"""
DoubleU-Net
===========
Paper: https://arxiv.org/abs/2006.04868

Two cascaded U-Nets:
  Network 1  — VGG-19 encoder → ASPP → decoder → output1
  Network 2  — lightweight encoder on (input × sigmoid(output1)) → ASPP → decoder → output2

Both outputs are supervised; the final prediction is output2.
Uses DiceFocal loss, matching the reference repo interface.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision.models import VGG19_Weights, vgg19

from src.losses import DiceFocalLoss

# ==============================================================================
# Building Blocks
# ==============================================================================


class Conv2D(nn.Module):
    """Conv → BN → (optional ReLU)."""

    def __init__(
        self,
        in_c: int,
        out_c: int,
        kernel_size: int = 3,
        padding: int = 1,
        dilation: int = 1,
        bias: bool = False,
        act: bool = True,
    ):
        super().__init__()
        self.act = act
        self.conv = nn.Sequential(
            nn.Conv2d(
                in_c,
                out_c,
                kernel_size=kernel_size,
                padding=padding,
                dilation=dilation,
                bias=bias,
            ),
            nn.BatchNorm2d(out_c),
        )
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.conv(x)
        if self.act:
            x = self.relu(x)
        return x


class SqueezeExcitation(nn.Module):
    """Channel attention via squeeze-and-excitation."""

    def __init__(self, in_channels: int, ratio: int = 8):
        super().__init__()
        self.avgpool = nn.AdaptiveAvgPool2d(1)
        self.fc = nn.Sequential(
            nn.Linear(in_channels, in_channels // ratio),
            nn.ReLU(inplace=True),
            nn.Linear(in_channels // ratio, in_channels),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        b, c, _, _ = x.size()
        y = self.avgpool(x).view(b, c)
        y = self.fc(y).view(b, c, 1, 1)
        return x * y.expand_as(x)


class ASPP(nn.Module):
    """Atrous Spatial Pyramid Pooling."""

    def __init__(self, in_c: int, out_c: int):
        super().__init__()
        self.avgpool = nn.Sequential(
            nn.AdaptiveAvgPool2d((2, 2)),
            Conv2D(in_c, out_c, kernel_size=1, padding=0),
        )
        self.c1 = Conv2D(in_c, out_c, kernel_size=1, padding=0, dilation=1)
        self.c2 = Conv2D(in_c, out_c, kernel_size=3, padding=6, dilation=6)
        self.c3 = Conv2D(in_c, out_c, kernel_size=3, padding=12, dilation=12)
        self.c4 = Conv2D(in_c, out_c, kernel_size=3, padding=18, dilation=18)
        self.c5 = Conv2D(out_c * 5, out_c, kernel_size=1, padding=0, dilation=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x0 = self.avgpool(x)
        x0 = F.interpolate(x0, size=x.size()[2:], mode="bilinear", align_corners=True)

        x1 = self.c1(x)
        x2 = self.c2(x)
        x3 = self.c3(x)
        x4 = self.c4(x)

        xc = torch.cat([x0, x1, x2, x3, x4], dim=1)
        return self.c5(xc)


class SEConvBlock(nn.Module):
    """Conv2D → Conv2D → SqueezeExcitation."""

    def __init__(self, in_c: int, out_c: int):
        super().__init__()
        self.c1 = Conv2D(in_c, out_c)
        self.c2 = Conv2D(out_c, out_c)
        self.se = SqueezeExcitation(out_c)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.c1(x)
        x = self.c2(x)
        x = self.se(x)
        return x


# ==============================================================================
# Network 1 — VGG-19 Encoder + Decoder
# ==============================================================================


class Encoder1(nn.Module):
    """VGG-19-based encoder (pretrained).

    Args:
        weights: Weights to pass to ``torchvision.models.vgg19``.
            Pass ``None`` to skip the pre-trained weight download (e.g.
            during inference when a full ``state_dict`` checkpoint is
            loaded afterwards).  Defaults to ``VGG19_Weights.DEFAULT``
            which preserves the existing training behaviour.
    """

    def __init__(self, weights=VGG19_Weights.DEFAULT):
        super().__init__()
        network = vgg19(weights=weights)
        self.x1 = network.features[:4]
        self.x2 = network.features[4:9]
        self.x3 = network.features[9:18]
        self.x4 = network.features[18:27]
        self.x5 = network.features[27:36]

    def forward(self, x: torch.Tensor):
        x1 = self.x1(x)
        x2 = self.x2(x1)
        x3 = self.x3(x2)
        x4 = self.x4(x3)
        x5 = self.x5(x4)
        return x5, [x4, x3, x2, x1]


class Decoder1(nn.Module):
    def __init__(self):
        super().__init__()
        self.up = nn.Upsample(scale_factor=2, mode="bilinear", align_corners=True)
        self.c1 = SEConvBlock(64 + 512, 256)
        self.c2 = SEConvBlock(512, 128)
        self.c3 = SEConvBlock(256, 64)
        self.c4 = SEConvBlock(128, 32)

    def forward(self, x: torch.Tensor, skip: list[torch.Tensor]) -> torch.Tensor:
        s1, s2, s3, s4 = skip

        x = self.up(x)
        x = torch.cat([x, s1], dim=1)
        x = self.c1(x)

        x = self.up(x)
        x = torch.cat([x, s2], dim=1)
        x = self.c2(x)

        x = self.up(x)
        x = torch.cat([x, s3], dim=1)
        x = self.c3(x)

        x = self.up(x)
        x = torch.cat([x, s4], dim=1)
        x = self.c4(x)

        return x


# ==============================================================================
# Network 2 — Lightweight Encoder + Decoder (with dual skip connections)
# ==============================================================================


class Encoder2(nn.Module):
    def __init__(self):
        super().__init__()
        self.pool = nn.MaxPool2d((2, 2))
        self.c1 = SEConvBlock(3, 32)
        self.c2 = SEConvBlock(32, 64)
        self.c3 = SEConvBlock(64, 128)
        self.c4 = SEConvBlock(128, 256)

    def forward(self, x: torch.Tensor):
        x1 = self.c1(x)
        p1 = self.pool(x1)

        x2 = self.c2(p1)
        p2 = self.pool(x2)

        x3 = self.c3(p2)
        p3 = self.pool(x3)

        x4 = self.c4(p3)
        p4 = self.pool(x4)

        return p4, [x4, x3, x2, x1]


class Decoder2(nn.Module):
    """Decoder that fuses skip connections from both encoder networks."""

    def __init__(self):
        super().__init__()
        self.up = nn.Upsample(scale_factor=2, mode="bilinear", align_corners=True)
        # Channel counts account for concatenation of bottleneck + skip1 + skip2
        self.c1 = SEConvBlock(832, 256)  # 320 + 512
        self.c2 = SEConvBlock(640, 128)  # 256 + 256 + 128
        self.c3 = SEConvBlock(320, 64)  # 128 + 128 + 64
        self.c4 = SEConvBlock(160, 32)  # 64 + 64 + 32

    def forward(
        self,
        x: torch.Tensor,
        skip1: list[torch.Tensor],
        skip2: list[torch.Tensor],
    ) -> torch.Tensor:
        x = self.up(x)
        x = torch.cat([x, skip1[0], skip2[0]], dim=1)
        x = self.c1(x)

        x = self.up(x)
        x = torch.cat([x, skip1[1], skip2[1]], dim=1)
        x = self.c2(x)

        x = self.up(x)
        x = torch.cat([x, skip1[2], skip2[2]], dim=1)
        x = self.c3(x)

        x = self.up(x)
        x = torch.cat([x, skip1[3], skip2[3]], dim=1)
        x = self.c4(x)

        return x


# ==============================================================================
# DoubleU-Net
# ==============================================================================


class DoubleUnet(nn.Module):
    def __init__(self, vgg19_weights=VGG19_Weights.DEFAULT):
        super().__init__()

        # Network 1
        # Pass the vgg19_weights parameter through so callers can disable
        # the pre-trained weight download when loading a full checkpoint.
        self.e1 = Encoder1(weights=vgg19_weights)
        self.a1 = ASPP(512, 64)
        self.d1 = Decoder1()
        self.y1 = nn.Conv2d(32, 1, kernel_size=1, padding=0)
        self.sigmoid = nn.Sigmoid()

        # Network 2
        self.e2 = Encoder2()
        self.a2 = ASPP(256, 64)
        self.d2 = Decoder2()
        self.y2 = nn.Conv2d(32, 1, kernel_size=1, padding=0)

        self.loss_fn = DiceFocalLoss(
            alpha=0.75, gamma=2.0, dice_weight=0.5, focal_weight=0.5
        )

    def forward(self, sample: dict) -> dict:
        x = sample["images"]
        y = sample.get("masks")

        # Network 1 forward
        x0 = x
        x_enc, skip1 = self.e1(x)
        x_enc = self.a1(x_enc)
        x_dec = self.d1(x_enc, skip1)
        y1 = self.y1(x_dec)

        # Gate the input with Network 1's prediction
        input_x = x0 * self.sigmoid(y1)

        # Network 2 forward
        x_enc2, skip2 = self.e2(input_x)
        x_enc2 = self.a2(x_enc2)
        x_dec2 = self.d2(x_enc2, skip1, skip2)
        y2 = self.y2(x_dec2)

        result: dict = {"prediction": y2}
        if y is not None:
            # Both outputs are supervised
            loss1 = self.loss_fn(y1, y)
            loss2 = self.loss_fn(y2, y)
            result["loss"] = loss1 + loss2

        return result
