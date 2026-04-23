"""Shared image preprocessing utilities for inference pipelines.

All functions operate on BGR float32 arrays in [0, 1], matching the
convention used by ``cv2.imread`` after normalisation.  This keeps the
interface consistent across single-stage and two-stage callers.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch


# ==============================================================================
# Image Loading
# ==============================================================================


def load_image(path: Path) -> np.ndarray:
    """Load an image from disk as a float32 BGR array in [0, 1].

    Args:
        path: Absolute or relative path to the image file.

    Returns:
        np.ndarray of shape (H, W, 3), dtype float32, values in [0, 1].

    Raises:
        FileNotFoundError: If ``path`` does not exist on disk.
        ValueError: If ``cv2.imread`` returns None (corrupted file or
            unsupported format).
    """
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {path}")

    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(
            f"cv2.imread returned None for {path} — "
            "file may be corrupted or in an unsupported format."
        )

    return img.astype(np.float32) / 255.0


# ==============================================================================
# Display Resizing
# ==============================================================================


def resize_for_display(img: np.ndarray, max_px: int) -> np.ndarray:
    """Resize an image so its longest edge is at most ``max_px`` pixels.

    Uses bilinear interpolation.  Returns the original array unchanged
    when both dimensions already fit within the limit.

    Args:
        img: Float32 BGR array of any shape (H, W, 3).
        max_px: Maximum allowed size for the longest edge.

    Returns:
        Resized (or unchanged) float32 BGR array.
    """
    h, w = img.shape[:2]
    if max(h, w) > max_px:
        scale = max_px / max(h, w)
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    return img


# ==============================================================================
# Tensor Preparation
# ==============================================================================


def prepare_tensor(
    img: np.ndarray,
    target_h: int,
    target_w: int,
    device: str,
) -> torch.Tensor:
    """Resize, transpose, and batch an image for model inference.

    Resize uses bilinear interpolation.  No channel normalisation is
    applied beyond the [0, 1] float conversion already done by
    ``load_image``.

    Args:
        img: Float32 BGR array of shape (H, W, 3), values in [0, 1].
        target_h: Target height for the model input.
        target_w: Target width for the model input.
        device: PyTorch device string (e.g. "cpu" or "cuda").

    Returns:
        Tensor of shape (1, 3, target_h, target_w), float32, on ``device``.
    """
    resized = cv2.resize(img, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
    # HWC → CHW, then add batch dimension.
    tensor = torch.from_numpy(resized).permute(2, 0, 1).unsqueeze(0).float()
    return tensor.to(device)


# ==============================================================================
# Logit → Mask Conversion
# ==============================================================================


def tensor_to_mask(
    logits: torch.Tensor,
    original_h: int,
    original_w: int,
) -> np.ndarray:
    """Convert raw model logits to a uint8 binary mask at original resolution.

    Pipeline: sigmoid → threshold at 0.5 → squeeze batch + channel dims
              → numpy → cv2.resize (nearest-neighbour) to (original_w, original_h).

    Args:
        logits: Raw output tensor from the segmentation model, any shape
            broadcastable to (1, 1, H, W) or (H, W).
        original_h: Target mask height.
        original_w: Target mask width.

    Returns:
        np.ndarray of shape (original_h, original_w), dtype uint8, values
        in {0, 255}.
    """
    prob = torch.sigmoid(logits)
    # Squeeze away batch and channel dims regardless of how the model
    # chose to arrange them.
    squeezed = (prob >= 0.5).squeeze().cpu().numpy().astype(np.uint8)
    # A (1, 1, H, W) tensor squeezed to a scalar when H=W=1; ensure 2-D.
    binary = np.atleast_2d(squeezed)
    mask_uint8 = binary * 255

    if mask_uint8.shape != (original_h, original_w):
        mask_uint8 = cv2.resize(
            mask_uint8, (original_w, original_h), interpolation=cv2.INTER_NEAREST
        )

    return mask_uint8
