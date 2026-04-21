"""
Attention U-Net — Oktay et al. 2018
=====================================
Paper: https://arxiv.org/abs/1804.03999

Attention gates are inserted on the skip connections between encoder
and decoder. Each gate reweights encoder feature maps using a gating
signal from the decoder, allowing the network to focus on relevant
regions automatically.

Architecture:
  Encoder: 4 ConvBlock + MaxPool stages with filters [64, 128, 256, 512]
  Bottleneck: 1 ConvBlock at 1024 channels
  Decoder: 4 UpConv + AttentionGate + concatenate + ConvBlock stages
  Output: 1×1 conv to 1 logit channel (no sigmoid — matches existing models)

Loss, forward signature, and output dict format match UNet / DoubleUnet
exactly so all three models are interchangeable in train.py / train_stage2.py.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

from src.losses import DiceFocalLoss


# ==============================================================================
# Building Blocks
# ==============================================================================


class ConvBlock(nn.Module):
    """Two sequential (Conv3×3 → BatchNorm → ReLU) blocks.

    Args:
        in_ch: Input channels.
        out_ch: Output channels.
    """

    def __init__(self, in_ch: int, out_ch: int) -> None:
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, kernel_size=3, stride=1, padding=1, bias=True),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, kernel_size=3, stride=1, padding=1, bias=True),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv(x)


class UpConv(nn.Module):
    """Bilinear upsample ×2 followed by 1×1 Conv → BN → ReLU to halve channels.

    Using bilinear upsampling (rather than transposed convolution) to match
    the plan's specification and avoid checkerboard artefacts.

    Args:
        in_ch: Input channels.
        out_ch: Output channels (typically in_ch // 2).
    """

    def __init__(self, in_ch: int, out_ch: int) -> None:
        super().__init__()
        self.up = nn.Sequential(
            nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False),
            nn.Conv2d(in_ch, out_ch, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.up(x)


class AttentionGate(nn.Module):
    """Attention gate from Oktay et al. 2018.

    Produces a soft attention map that reweights skip-connection features
    based on a gating signal from the decoder. This lets the network
    suppress irrelevant activations in background regions.

    Implementation:
        alpha = sigmoid( W_psi( ReLU( W_g(g) + W_x(x) ) ) )
        output = x * alpha

    Args:
        F_g: Channels in gating signal g (from decoder path after UpConv).
        F_l: Channels in skip connection x (from encoder path).
        F_int: Intermediate channel count — typically F_l // 2.
    """

    def __init__(self, F_g: int, F_l: int, F_int: int) -> None:
        super().__init__()

        # 1×1 conv to project both signals into the same F_int space
        self.W_g = nn.Sequential(
            nn.Conv2d(F_g, F_int, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(F_int),
        )
        self.W_x = nn.Sequential(
            nn.Conv2d(F_l, F_int, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(F_int),
        )

        # Collapse to a single attention coefficient per spatial location
        self.psi = nn.Sequential(
            nn.Conv2d(F_int, 1, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(1),
            nn.Sigmoid(),
        )

        self.relu = nn.ReLU(inplace=True)

    def forward(self, g: torch.Tensor, x: torch.Tensor) -> torch.Tensor:
        """Compute attention-weighted skip features.

        Args:
            g: Gating signal from decoder, shape (B, F_g, H, W).
            x: Skip connection from encoder, shape (B, F_l, H, W).
               May have larger spatial dims than g when strides differ;
               g is bilinearly upsampled to match x before adding.
        Returns:
            Attention-weighted x, shape (B, F_l, H, W).
        """
        g1 = self.W_g(g)
        x1 = self.W_x(x)

        # g1 and x1 must have matching spatial dims for element-wise addition.
        # After UpConv the decoder feature g should already match x; this
        # interpolation is a safety fallback for odd input sizes.
        if g1.shape[2:] != x1.shape[2:]:
            g1 = F.interpolate(g1, size=x1.shape[2:], mode="bilinear", align_corners=False)

        alpha = self.psi(self.relu(g1 + x1))
        return x * alpha


# ==============================================================================
# Full Network
# ==============================================================================


class AttentionUNet(nn.Module):
    """Attention U-Net for binary segmentation (Oktay et al. 2018).

    Encoder–decoder architecture with attention gates on every skip connection.
    Filter progression mirrors the standard UNet: [64, 128, 256, 512, 1024].
    Input must be divisible by 16 (4 downsampling stages of ×2).

    Loss is computed internally using DiceFocalLoss, matching the contract
    of UNet and DoubleUnet so all three models are interchangeable.

    Args:
        in_channels: Input image channels (default 3 for BGR).
        out_channels: Output logit channels (default 1 for binary segmentation).
    """

    def __init__(self, in_channels: int = 3, out_channels: int = 1) -> None:
        super().__init__()

        filters = [64, 128, 256, 512, 1024]

        # ------------------------------------------------------------------
        # Encoder
        # ------------------------------------------------------------------
        self.Conv1 = ConvBlock(in_channels, filters[0])
        self.Pool1 = nn.MaxPool2d(kernel_size=2, stride=2)

        self.Conv2 = ConvBlock(filters[0], filters[1])
        self.Pool2 = nn.MaxPool2d(kernel_size=2, stride=2)

        self.Conv3 = ConvBlock(filters[1], filters[2])
        self.Pool3 = nn.MaxPool2d(kernel_size=2, stride=2)

        self.Conv4 = ConvBlock(filters[2], filters[3])
        self.Pool4 = nn.MaxPool2d(kernel_size=2, stride=2)

        # ------------------------------------------------------------------
        # Bottleneck
        # ------------------------------------------------------------------
        self.Conv5 = ConvBlock(filters[3], filters[4])

        # ------------------------------------------------------------------
        # Decoder
        # Each stage: UpConv → AttentionGate on skip → concat → ConvBlock
        # UpConv halves channels; after concat with attention-weighted skip,
        # the ConvBlock takes filters[i]*2 in and outputs filters[i].
        # ------------------------------------------------------------------

        # Stage 4 (bottleneck → 512)
        self.Up5 = UpConv(filters[4], filters[3])
        self.Att5 = AttentionGate(F_g=filters[3], F_l=filters[3], F_int=filters[2])
        self.UpConv5 = ConvBlock(filters[4], filters[3])

        # Stage 3 (512 → 256)
        self.Up4 = UpConv(filters[3], filters[2])
        self.Att4 = AttentionGate(F_g=filters[2], F_l=filters[2], F_int=filters[1])
        self.UpConv4 = ConvBlock(filters[3], filters[2])

        # Stage 2 (256 → 128)
        self.Up3 = UpConv(filters[2], filters[1])
        self.Att3 = AttentionGate(F_g=filters[1], F_l=filters[1], F_int=filters[0])
        self.UpConv3 = ConvBlock(filters[2], filters[1])

        # Stage 1 (128 → 64)
        self.Up2 = UpConv(filters[1], filters[0])
        self.Att2 = AttentionGate(F_g=filters[0], F_l=filters[0], F_int=filters[0] // 2)
        self.UpConv2 = ConvBlock(filters[1], filters[0])

        # ------------------------------------------------------------------
        # Output head — raw logits, no sigmoid (matches UNet convention)
        # ------------------------------------------------------------------
        self.OutConv = nn.Conv2d(filters[0], out_channels, kernel_size=1)

        self.loss_fn = DiceFocalLoss(
            alpha=0.75, gamma=2.0, dice_weight=0.5, focal_weight=0.5
        )

    def forward(self, inputs: dict) -> dict:
        """Encode, attend, decode, compute loss if masks are present.

        Args:
            inputs: {
                "images": Tensor(B, C, H, W),
                "masks":  Tensor(B, 1, H, W)  — optional; if absent, loss is not computed.
            }
        Returns:
            {"prediction": Tensor(B, 1, H, W) logits, "loss": scalar}  when masks provided.
            {"prediction": Tensor(B, 1, H, W) logits}                  otherwise.
        """
        x = inputs["images"]
        y = inputs.get("masks")

        # ------------------------------------------------------------------
        # Encoder path — save skip connections for attention
        # ------------------------------------------------------------------
        e1 = self.Conv1(x)

        e2 = self.Pool1(e1)
        e2 = self.Conv2(e2)

        e3 = self.Pool2(e2)
        e3 = self.Conv3(e3)

        e4 = self.Pool3(e3)
        e4 = self.Conv4(e4)

        # Bottleneck
        e5 = self.Pool4(e4)
        e5 = self.Conv5(e5)

        # ------------------------------------------------------------------
        # Decoder path — upsample, apply attention gate, concatenate, convolve
        # ------------------------------------------------------------------

        # Stage 4: upsample from bottleneck → apply attention to e4 → concat → conv
        d5 = self.Up5(e5)
        e4_att = self.Att5(g=d5, x=e4)
        d5 = torch.cat((e4_att, d5), dim=1)
        d5 = self.UpConv5(d5)

        # Stage 3
        d4 = self.Up4(d5)
        e3_att = self.Att4(g=d4, x=e3)
        d4 = torch.cat((e3_att, d4), dim=1)
        d4 = self.UpConv4(d4)

        # Stage 2
        d3 = self.Up3(d4)
        e2_att = self.Att3(g=d3, x=e2)
        d3 = torch.cat((e2_att, d3), dim=1)
        d3 = self.UpConv3(d3)

        # Stage 1
        d2 = self.Up2(d3)
        e1_att = self.Att2(g=d2, x=e1)
        d2 = torch.cat((e1_att, d2), dim=1)
        d2 = self.UpConv2(d2)

        out = self.OutConv(d2)

        result: dict = {"prediction": out}
        if y is not None:
            result["loss"] = self.loss_fn(out, y)
        return result
