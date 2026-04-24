"""Single-stage caries segmentation pipeline.

Runs a segmentation model directly on the full panoramic radiograph.
No tooth detection step is involved — the model operates on the whole
image at once.

Shared data structures (``BBox``, ``InferenceOutput``) are defined here
because single-stage is the simpler pipeline; two_stage.py imports them.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import torch
import torch.nn as nn

from app.core.config import Settings
from app.core.storage import save_display_copy, save_mask
from app.inference.preprocessing import load_image, prepare_tensor, tensor_to_mask
from app.models.image_result import ImageResult


# ==============================================================================
# Shared data structures
# ==============================================================================


@dataclass
class BBox:
    """Axis-aligned bounding box from YOLO detection (pixel coordinates)."""

    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float


@dataclass
class InferenceOutput:
    """Result produced by either pipeline after processing one image."""

    display_path: Path
    mask_path: Path
    # None for single-stage; populated list (possibly empty) for two-stage.
    bounding_boxes: list[BBox] | None
    inference_time_ms: int
    original_size: dict[str, int]  # {"width": W, "height": H}


# ==============================================================================
# Single-stage runner
# ==============================================================================


def run_single_stage(
    image_result: ImageResult,
    model: nn.Module,
    settings: Settings,
) -> InferenceOutput:
    """Run single-stage caries segmentation on one upload.

    Steps:
        1. Load the raw upload as a float32 BGR array.
        2. Save a display-resized copy (longest edge ≤ MAX_DISPLAY_PX).
        3. Prepare a (1, 3, 384, 384) tensor for the model.
        4. Forward pass with ``torch.no_grad()``.
        5. Convert logits to a binary mask and save it.

    Args:
        image_result: ORM row with ``upload_path`` populated.
        model: Loaded segmentation model in eval mode on the target device.
        settings: App settings for paths and device selection.

    Returns:
        ``InferenceOutput`` with ``bounding_boxes=None``.
    """
    upload_path = Path(image_result.upload_path)
    img = load_image(upload_path)
    h, w = img.shape[:2]
    device = settings.resolved_device

    # Save the display-sized copy so the file-serving endpoint has a
    # browser-ready PNG regardless of the original image dimensions.
    display_path = save_display_copy(
        img=img,
        image_result_id=uuid.UUID(str(image_result.id)),
        settings=settings,
    )

    # Resize and batch for the model input; 384×384 is the training resolution
    # for single-stage checkpoints.
    tensor = prepare_tensor(img, target_h=384, target_w=384, device=device)

    t_start = time.monotonic()
    with torch.no_grad():
        output = model({"images": tensor})
    inference_ms = int((time.monotonic() - t_start) * 1000)

    logits = output["prediction"]
    mask = tensor_to_mask(logits, original_h=h, original_w=w)

    mask_path = save_mask(
        mask=mask,
        image_result_id=uuid.UUID(str(image_result.id)),
        settings=settings,
    )

    return InferenceOutput(
        display_path=display_path,
        mask_path=mask_path,
        bounding_boxes=None,
        inference_time_ms=inference_ms,
        original_size={"width": w, "height": h},
    )
