"""Two-stage caries segmentation pipeline.

Stage 1: YOLO detects individual teeth on the full panoramic.
Stage 2: A segmentation model runs on each padded tooth crop.
         Per-crop masks are composed back onto a full-size canvas using
         ``np.maximum`` (union semantics) so that overlapping crops are
         OR-ed rather than overwritten.

Bounding boxes returned in ``InferenceOutput`` are the raw YOLO xyxy
coordinates on the original image — not the padded crops — so the
frontend can draw them on top of the overlay canvas.

Data structures are imported from ``single_stage`` to keep a single
definition for ``BBox`` and ``InferenceOutput``.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import torch
import torch.nn as nn

from app.core.config import Settings
from app.core.storage import save_display_copy, save_mask
from app.inference.preprocessing import load_image, prepare_tensor, tensor_to_mask
from app.inference.single_stage import BBox, InferenceOutput
from app.models.image_result import ImageResult

if TYPE_CHECKING:
    from ultralytics import YOLO


def run_two_stage(
    image_result: ImageResult,
    yolo: "YOLO",
    seg_model: nn.Module,
    settings: Settings,
) -> InferenceOutput:
    """Run two-stage pipeline: YOLO tooth detection then per-crop segmentation.

    Steps:
        1. Load the raw upload and save a display copy.
        2. Run YOLO on the full-size image (uint8 BGR) to get tooth boxes.
        3. If no detections: return an all-zero mask and empty bbox list.
        4. For each detection:
            a. Pad the bbox by 10 % on each side, clamped to image bounds.
            b. Crop from the float image array.
            c. Prepare a (1, 3, 256, 256) tensor for the segmentation model.
            d. Forward pass with ``torch.no_grad()``.
            e. ``tensor_to_mask`` resized to padded-crop dimensions.
            f. Paste onto the full-size canvas using ``np.maximum``.
        5. Save the composed mask and return ``InferenceOutput``.

    Note:
        ``bounding_boxes`` in the response are the raw (unpadded) YOLO
        xyxy coordinates for overlay drawing in the frontend.

    Args:
        image_result: ORM row with ``upload_path`` populated.
        yolo: Loaded Ultralytics YOLO model for tooth detection.
        seg_model: Loaded segmentation model in eval mode.
        settings: App settings for paths and device selection.

    Returns:
        ``InferenceOutput`` with ``bounding_boxes`` populated (may be empty
        if YOLO found no teeth).
    """
    upload_path = Path(image_result.upload_path)
    img = load_image(upload_path)
    h, w = img.shape[:2]
    result_id = uuid.UUID(str(image_result.id))

    display_path = save_display_copy(img=img, image_result_id=result_id, settings=settings)

    # YOLO expects a uint8 BGR array (same format OpenCV produces).
    img_uint8 = (img * 255).clip(0, 255).astype(np.uint8)
    yolo_results = yolo.predict(img_uint8, conf=0.25, verbose=False)

    # Parse detections into BBox objects.  The YOLO Results object stores
    # coordinates in xyxy format with shape (N, 4) and confidences with
    # shape (N,).
    boxes: list[BBox] = []
    if yolo_results and yolo_results[0].boxes is not None:
        raw = yolo_results[0].boxes
        xyxy = raw.xyxy.cpu().numpy()   # (N, 4)
        confs = raw.conf.cpu().numpy()  # (N,)
        for i in range(len(xyxy)):
            boxes.append(
                BBox(
                    x1=int(xyxy[i][0]),
                    y1=int(xyxy[i][1]),
                    x2=int(xyxy[i][2]),
                    y2=int(xyxy[i][3]),
                    confidence=float(confs[i]),
                )
            )

    # Zero-detection case: return an all-black mask and an empty bbox list.
    # The frontend will display a "No detections" badge.
    if not boxes:
        mask_path = save_mask(
            mask=np.zeros((h, w), dtype=np.uint8),
            image_result_id=result_id,
            settings=settings,
        )
        return InferenceOutput(
            display_path=display_path,
            mask_path=mask_path,
            bounding_boxes=[],
            inference_time_ms=0,
            original_size={"width": w, "height": h},
        )

    # Composition canvas — same spatial size as the original image.
    canvas = np.zeros((h, w), dtype=np.uint8)

    t_start = time.monotonic()

    for bbox in boxes:
        # ==================================================================
        # 10 % padding, clamped to image bounds.
        #
        # Padding ensures that the crop includes some context around the
        # tooth boundary, which improves segmentation quality at the edges.
        # ==================================================================
        pw = int((bbox.x2 - bbox.x1) * 0.10)
        ph = int((bbox.y2 - bbox.y1) * 0.10)
        px1 = max(0, bbox.x1 - pw)
        py1 = max(0, bbox.y1 - ph)
        px2 = min(w, bbox.x2 + pw)
        py2 = min(h, bbox.y2 + ph)

        crop = img[py1:py2, px1:px2]  # (crop_h, crop_w, 3) float32
        crop_h = py2 - py1
        crop_w = px2 - px1

        # 256×256 is the training resolution for two-stage checkpoints.
        tensor = prepare_tensor(crop, target_h=256, target_w=256, device=settings.DEVICE)

        with torch.no_grad():
            output = seg_model({"images": tensor})

        # Resize the crop mask back to the padded-crop spatial dimensions
        # before pasting it onto the full canvas.
        crop_mask = tensor_to_mask(output["prediction"], original_h=crop_h, original_w=crop_w)

        # Union semantics: a pixel is "caries" if any crop marks it as such.
        canvas[py1:py2, px1:px2] = np.maximum(canvas[py1:py2, px1:px2], crop_mask)

    inference_ms = int((time.monotonic() - t_start) * 1000)

    mask_path = save_mask(mask=canvas, image_result_id=result_id, settings=settings)

    return InferenceOutput(
        display_path=display_path,
        mask_path=mask_path,
        bounding_boxes=boxes,
        inference_time_ms=inference_ms,
        original_size={"width": w, "height": h},
    )
