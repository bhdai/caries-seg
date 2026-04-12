import torch
import torch.nn as nn
import torch.nn.functional as F


class FocalLoss(nn.Module):
    """Binary focal loss operating on raw logits."""

    def __init__(self, alpha: float = 0.75, gamma: float = 2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, inputs: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        probs = torch.sigmoid(inputs)
        targets = targets.float()

        bce_loss = F.binary_cross_entropy_with_logits(inputs, targets, reduction="none")

        p_t = probs * targets + (1 - probs) * (1 - targets)
        focal_weight = (1 - p_t) ** self.gamma
        alpha_t = self.alpha * targets + (1 - self.alpha) * (1 - targets)

        loss = alpha_t * focal_weight * bce_loss
        return loss.mean()


class DiceFocalLoss(nn.Module):
    """Combined Dice + Focal loss for binary segmentation."""

    def __init__(
        self,
        alpha: float = 0.75,
        gamma: float = 2.0,
        smooth: float = 1.0,
        dice_weight: float = 0.5,
        focal_weight: float = 0.5,
    ):
        super().__init__()
        self.focal = FocalLoss(alpha=alpha, gamma=gamma)
        self.smooth = smooth
        self.dice_weight = dice_weight
        self.focal_weight = focal_weight

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        # Dice loss
        probs = torch.sigmoid(logits)
        probs_flat = probs.view(-1)
        targets_flat = targets.view(-1).float()
        intersection = (probs_flat * targets_flat).sum()
        dice_loss = 1 - (2.0 * intersection + self.smooth) / (
            probs_flat.sum() + targets_flat.sum() + self.smooth
        )

        focal_loss = self.focal(logits, targets)
        return self.dice_weight * dice_loss + self.focal_weight * focal_loss


def DiceBCELoss(
    inputs: torch.Tensor, targets: torch.Tensor, smooth: float = 1.0
) -> torch.Tensor:
    """Dice + BCE loss (functional form)."""
    inputs = torch.sigmoid(inputs)
    inputs_flat = inputs.view(-1)
    targets_flat = targets.view(-1)

    intersection = (inputs_flat * targets_flat).sum()
    dice_loss = 1 - (2.0 * intersection + smooth) / (
        inputs_flat.sum() + targets_flat.sum() + smooth
    )
    bce = F.binary_cross_entropy(inputs_flat, targets_flat, reduction="mean")
    return bce + dice_loss
