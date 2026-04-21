"""Visually Inspect YOLO Tooth Detections on DC1000 Images
==========================================================

Runs the trained YOLO model on a small random sample of DC1000 images and
saves annotated outputs (detected bboxes + confidence scores drawn over the
image). Also overlays the ground-truth caries mask as a colour tint so you
can judge whether detections cover the relevant teeth.

This is Step 2.3 of the plan: confirming that YOLO generalises from Tufts
(840×1615) to DC1000 (1435×2943) despite the domain shift.

Output::

    files/yolo_inspect/
      {stem}_detections.png   — image with bbox overlays
      summary.txt             — per-image detection count and confidence stats

Usage::

    # Default: 5 random images from DC1000 train split
    python scripts/inspect_yolo.py

    # Custom sample size, split, confidence threshold
    python scripts/inspect_yolo.py --n 10 --split valid --conf 0.1

    # Specific YOLO weights
    python scripts/inspect_yolo.py --weights files/yolo_tooth/train/weights/best.pt
"""

import argparse
import random
import sys
from pathlib import Path

import cv2
import numpy as np


# ==============================================================================
# Drawing helpers
# ==============================================================================

# Colour palette: bbox in bright green, caries mask tint in semi-transparent red
BBOX_COLOUR = (0, 255, 0)       # BGR green
BBOX_THICKNESS = 3
LABEL_COLOUR = (0, 255, 0)
LABEL_BG = (0, 0, 0)
MASK_TINT = (0, 0, 200)         # BGR red tint for caries regions
MASK_ALPHA = 0.35               # blend strength for mask overlay


def draw_detections(
    image: np.ndarray,
    mask: np.ndarray,
    boxes: np.ndarray,
    confs: np.ndarray,
) -> np.ndarray:
    """Overlay caries mask tint and YOLO bbox detections on image.

    Args:
        image: BGR image, shape (H, W, 3), uint8.
        mask:  Grayscale mask, shape (H, W), uint8 — values 0 or 255.
        boxes: Detected bboxes, shape (N, 4), float — [x1, y1, x2, y2] pixels.
        confs: Detection confidences, shape (N,), float.

    Returns:
        Annotated BGR image copy.
    """
    vis = image.copy()

    # --- caries mask overlay ------------------------------------------------
    if mask is not None and mask.max() > 0:
        caries_region = mask > 127
        tint = np.zeros_like(vis)
        tint[caries_region] = MASK_TINT
        vis = cv2.addWeighted(vis, 1.0, tint, MASK_ALPHA, 0)

    # --- bbox overlays -------------------------------------------------------
    for box, conf in zip(boxes, confs):
        x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
        cv2.rectangle(vis, (x1, y1), (x2, y2), BBOX_COLOUR, BBOX_THICKNESS)

        label = f"{conf:.2f}"
        (tw, th), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
        cv2.rectangle(vis, (x1, y1 - th - baseline - 4), (x1 + tw + 4, y1), LABEL_BG, -1)
        cv2.putText(
            vis, label,
            (x1 + 2, y1 - baseline - 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            LABEL_COLOUR,
            1,
            cv2.LINE_AA,
        )

    return vis


# ==============================================================================
# Entry point
# ==============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visually inspect YOLO tooth detections on DC1000 images."
    )
    parser.add_argument(
        "--weights",
        type=str,
        default="files/yolo_tooth/train/weights/best.pt",
        help="Path to trained YOLO weights (default: files/yolo_tooth/train/weights/best.pt)",
    )
    parser.add_argument(
        "--dc1000",
        type=str,
        default="data/DC1000",
        help="Root of the DC1000 dataset (default: data/DC1000)",
    )
    parser.add_argument(
        "--split",
        type=str,
        default="train",
        choices=["train", "valid", "test"],
        help="DC1000 split to sample from (default: train)",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=5,
        help="Number of images to inspect (default: 5)",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="YOLO confidence threshold (default: 0.25)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="files/yolo_inspect",
        help="Directory to save annotated images (default: files/yolo_inspect)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for image sampling (default: 42)",
    )
    args = parser.parse_args()

    weights_path = Path(args.weights)
    dc1000_root = Path(args.dc1000)
    output_dir = Path(args.output)

    # ------------------------------------------------------------------
    # Pre-flight validation
    # ------------------------------------------------------------------
    if not weights_path.exists():
        print(
            f"ERROR: YOLO weights not found: {weights_path}\n"
            "       Train the model first with  python scripts/train_yolo.py",
            file=sys.stderr,
        )
        sys.exit(1)

    images_dir = dc1000_root / args.split / "images"
    masks_dir = dc1000_root / args.split / "masks"

    if not images_dir.exists():
        print(
            f"ERROR: DC1000 images directory not found: {images_dir}",
            file=sys.stderr,
        )
        sys.exit(1)

    image_paths = sorted(images_dir.glob("*.png"))
    if not image_paths:
        print(f"ERROR: No .png images found in {images_dir}", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Sample images
    # ------------------------------------------------------------------
    rng = random.Random(args.seed)
    sample = rng.sample(image_paths, min(args.n, len(image_paths)))
    print(f"Sampling {len(sample)} image(s) from {images_dir}")

    # ------------------------------------------------------------------
    # Load YOLO model
    # ------------------------------------------------------------------
    from ultralytics import YOLO  # noqa: PLC0415

    model = YOLO(str(weights_path))
    print(f"Loaded weights: {weights_path}")

    # ------------------------------------------------------------------
    # Create output directory
    # ------------------------------------------------------------------
    output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Run inference and save annotated images
    # ------------------------------------------------------------------
    summary_lines: list[str] = [
        f"YOLO Inspection — {args.split} split, conf ≥ {args.conf}\n"
        f"Weights: {weights_path}\n"
        f"{'─' * 60}\n"
    ]

    for img_path in sample:
        image = cv2.imread(str(img_path))
        if image is None:
            print(f"  WARNING: could not read {img_path} — skipping")
            continue
        img_h, img_w = image.shape[:2]

        # Load corresponding mask if it exists (best-effort — may not exist
        # for every split variant; gracefully skip if absent)
        mask_path = masks_dir / img_path.name
        mask = None
        if mask_path.exists():
            mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)

        # Run YOLO inference
        results = model.predict(image, conf=args.conf, verbose=False)
        boxes = results[0].boxes.xyxy.cpu().numpy()   # (N, 4) — x1 y1 x2 y2
        confs = results[0].boxes.conf.cpu().numpy()   # (N,)
        n_det = len(boxes)

        # Warn on suspiciously low detection count
        if n_det == 0:
            print(f"  WARNING: 0 detections for {img_path.name} — possible domain-shift issue")
        elif n_det < 5:
            print(f"  NOTE: only {n_det} detection(s) for {img_path.name}")

        # Draw annotations
        vis = draw_detections(image, mask, boxes, confs)

        # Burn detection count and image info into top-left corner
        info = f"{img_path.name} | {img_w}x{img_h} | {n_det} teeth detected"
        cv2.putText(
            vis, info,
            (10, 36),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        out_path = output_dir / f"{img_path.stem}_detections.png"
        cv2.imwrite(str(out_path), vis)
        print(f"  {img_path.name}: {n_det} detections → {out_path}")

        # Summary stats
        conf_str = (
            f"min={confs.min():.3f} max={confs.max():.3f} mean={confs.mean():.3f}"
            if n_det > 0
            else "no detections"
        )
        summary_lines.append(
            f"{img_path.name}: {n_det} teeth | conf [{conf_str}]"
        )

    # ------------------------------------------------------------------
    # Write summary
    # ------------------------------------------------------------------
    summary_path = output_dir / "summary.txt"
    summary_path.write_text("\n".join(summary_lines) + "\n")
    print(f"\nSummary written to {summary_path}")
    print(f"Annotated images saved to {output_dir}/")
    print(
        "\nLegend:\n"
        "  Green boxes    — YOLO tooth detections (confidence printed on box)\n"
        "  Red tint       — ground-truth caries mask region\n"
        "  Good result    — boxes cover most teeth, red regions land inside boxes\n"
    )


if __name__ == "__main__":
    main()
