"""Extract Tooth Crops from DC1000 using Trained YOLO Model
============================================================

Phase 3 of the two-stage pipeline. Runs the trained YOLO tooth-detection
model over all DC1000 panoramic images and crops individual tooth regions
(plus their corresponding caries masks) to disk.

Output layout::

    data/DC1000_cropped/
      train/images/{pano_stem}_tooth_{idx:03d}.png   # BGR tooth crop
      train/masks/{pano_stem}_tooth_{idx:03d}.png    # binary mask crop
      valid/images/…
      valid/masks/…
      test/images/…
      test/masks/…
      metadata.json                 # one record per crop across all splits
      balanced/
        train_balanced.json         # filename list for 1:1 balanced training

Metadata record schema::

    {
      "filename":      "{pano_stem}_tooth_{idx:03d}.png",
      "source_image":  "0001.png",
      "split":         "train" | "valid" | "test",
      "bbox_original": [x1, y1, x2, y2],   # raw YOLO detection (pixels)
      "bbox_padded":   [x1, y1, x2, y2],   # after 10% padding + clamping
      "confidence":    0.87,
      "has_caries":    true | false,        # any white pixel in mask crop
      "original_size": [img_h, img_w]
    }

Usage::

    # Default settings (YOLO weights at files/yolo_tooth/train/weights/best.pt)
    python scripts/extract_tooth_crops.py

    # Custom paths and confidence threshold
    python scripts/extract_tooth_crops.py \\
        --yolo-weights files/yolo_tooth/train/weights/best.pt \\
        --dc1000-path data/DC1000 \\
        --output data/DC1000_cropped \\
        --conf-threshold 0.25 \\
        --padding 0.1 \\
        --seed 42
"""

import argparse
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np


# ==============================================================================
# Bbox Padding
# ==============================================================================


def add_padding(
    bbox: tuple[int, int, int, int],
    pad_frac: float,
    img_h: int,
    img_w: int,
) -> tuple[int, int, int, int]:
    """Expand a bbox by pad_frac of its dimensions, clamped to image bounds.

    Args:
        bbox: (x1, y1, x2, y2) in pixel coordinates — YOLO xyxy format where
            (x1, y1) is the top-left corner and (x2, y2) is the bottom-right.
        pad_frac: Fraction of each bbox dimension to add as margin on each side.
            0.1 adds 10% of the bbox width to both left and right, and 10% of
            the bbox height to both top and bottom.
        img_h: Image height in pixels — used to clamp the padded bbox.
        img_w: Image width in pixels — used to clamp the padded bbox.

    Returns:
        (x1_pad, y1_pad, x2_pad, y2_pad) padded and clamped to [0, img_w/img_h].
    """
    x1, y1, x2, y2 = bbox

    # Compute padding amounts in pixels based on the original bbox dimensions.
    # We pad each side independently so the added margin scales with tooth size.
    pad_x = int((x2 - x1) * pad_frac)
    pad_y = int((y2 - y1) * pad_frac)

    x1_pad = max(0, x1 - pad_x)
    y1_pad = max(0, y1 - pad_y)
    x2_pad = min(img_w, x2 + pad_x)
    y2_pad = min(img_h, y2 + pad_y)

    return x1_pad, y1_pad, x2_pad, y2_pad


# ==============================================================================
# Crop and Save
# ==============================================================================


def crop_and_save(
    image: np.ndarray,
    mask: np.ndarray,
    bbox: tuple[int, int, int, int],
    img_dir: Path,
    mask_dir: Path,
    filename: str,
) -> dict:
    """Crop the padded bbox region from image and mask, save both to disk.

    The mask is saved as-is (no binarisation) so we preserve the original
    0/255 values. Binarisation happens in the dataset loader at training time.

    Args:
        image: Full panoramic image as a BGR numpy array (H, W, 3).
        mask: Full panoramic caries mask as a grayscale numpy array (H, W).
        bbox: (x1, y1, x2, y2) padded bbox in pixel coordinates.
        img_dir: Directory to save the image crop.
        mask_dir: Directory to save the mask crop.
        filename: Stem filename (e.g., "0001_tooth_002.png") used for both.

    Returns:
        Partial metadata dict with keys: filename, bbox_padded, has_caries.
        Callers are expected to add source_image, split, bbox_original,
        confidence, and original_size before appending to the metadata list.
    """
    x1, y1, x2, y2 = bbox

    crop_img = image[y1:y2, x1:x2]
    crop_mask = mask[y1:y2, x1:x2]

    # A crop has caries if any pixel in its mask exceeds 127 (i.e., is 255
    # in the original binary 0/255 masks).
    has_caries = bool((crop_mask > 127).any())

    cv2.imwrite(str(img_dir / filename), crop_img)
    cv2.imwrite(str(mask_dir / filename), crop_mask)

    return {
        "filename": filename,
        "bbox_padded": list(bbox),
        "has_caries": has_caries,
    }


# ==============================================================================
# Balanced Split Creation
# ==============================================================================


def create_balanced_split(metadata: list[dict], seed: int) -> list[str]:
    """Create a 1:1 balanced list of training filenames.

    Counts caries-positive and caries-negative crops in the train split,
    then undersamples the majority class to match the minority count.
    This avoids duplicating samples while keeping the dataset balanced.

    Args:
        metadata: Full metadata list (all splits). Records for non-train
            splits are ignored.
        seed: Random seed for reproducible undersampling.

    Returns:
        Sorted list of filenames (just the basename, not the full path) for
        the balanced training subset.
    """
    train_records = [m for m in metadata if m["split"] == "train"]

    caries = [m["filename"] for m in train_records if m["has_caries"]]
    non_caries = [m["filename"] for m in train_records if not m["has_caries"]]

    minority_count = min(len(caries), len(non_caries))

    rng = random.Random(seed)
    if len(caries) > len(non_caries):
        caries = rng.sample(caries, minority_count)
    else:
        non_caries = rng.sample(non_caries, minority_count)

    return sorted(caries + non_caries)


# ==============================================================================
# Entry Point
# ==============================================================================


def main() -> None:
    """Run YOLO tooth detection on DC1000, extract crops, build metadata and
    a balanced training filename list.

    CLI args:
      --yolo-weights    Path to trained YOLO best.pt (default: files/yolo_tooth/train/weights/best.pt)
      --dc1000-path     Root of the DC1000 dataset (default: data/DC1000)
      --output          Output directory for crops (default: data/DC1000_cropped)
      --conf-threshold  YOLO confidence threshold (default: 0.25)
      --padding         Bbox padding fraction (default: 0.1)
      --seed            Random seed for balanced split (default: 42)
    """
    parser = argparse.ArgumentParser(
        description="Extract per-tooth crops from DC1000 using a trained YOLO model."
    )
    parser.add_argument(
        "--yolo-weights",
        default="files/yolo_tooth/train/weights/best.pt",
        help="Path to trained YOLO best.pt (default: files/yolo_tooth/train/weights/best.pt)",
    )
    parser.add_argument(
        "--dc1000-path",
        default="data/DC1000",
        help="Root directory of the DC1000 dataset (default: data/DC1000)",
    )
    parser.add_argument(
        "--output",
        default="data/DC1000_cropped",
        help="Output root directory for cropped dataset (default: data/DC1000_cropped)",
    )
    parser.add_argument(
        "--conf-threshold",
        type=float,
        default=0.25,
        help="YOLO confidence threshold for detections (default: 0.25)",
    )
    parser.add_argument(
        "--padding",
        type=float,
        default=0.1,
        help="Fraction of bbox dimension to add as padding on each side (default: 0.1)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for balanced split undersampling (default: 42)",
    )
    args = parser.parse_args()

    dc1000_path = Path(args.dc1000_path)
    output_path = Path(args.output)
    weights_path = Path(args.yolo_weights)

    # ------------------------------------------------------------------
    # Validate inputs
    # ------------------------------------------------------------------
    if not weights_path.exists():
        print(
            f"ERROR: YOLO weights not found: {weights_path}\n"
            "       Run scripts/train_yolo.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not dc1000_path.exists():
        print(f"ERROR: DC1000 dataset not found: {dc1000_path}", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Load YOLO model
    #
    # Ultralytics is imported here (not at module level) so that the script
    # can be imported or syntax-checked without requiring YOLO to be installed.
    # ------------------------------------------------------------------
    from ultralytics import YOLO  # noqa: PLC0415

    print(f"Loading YOLO model from {weights_path} …")
    model = YOLO(str(weights_path))

    # ------------------------------------------------------------------
    # Create output directory structure for all three splits
    # ------------------------------------------------------------------
    splits = ["train", "valid", "test"]
    for split in splits:
        (output_path / split / "images").mkdir(parents=True, exist_ok=True)
        (output_path / split / "masks").mkdir(parents=True, exist_ok=True)
    (output_path / "balanced").mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Main extraction loop
    #
    # For each DC1000 split we iterate over every panoramic image, run YOLO
    # inference, and save one crop per detected tooth.  We accumulate all
    # metadata in a flat list and write it once at the end.
    # ------------------------------------------------------------------
    all_metadata: list[dict] = []

    # Per-split stats for the summary printed at the end
    split_stats: dict[str, dict] = {}

    for split in splits:
        images_dir = dc1000_path / split / "images"
        masks_dir = dc1000_path / split / "masks"

        if not images_dir.exists():
            print(f"  WARNING: split directory not found: {images_dir} — skipping")
            continue

        image_paths = sorted(images_dir.glob("*.png"))
        if not image_paths:
            print(f"  WARNING: no .png images found in {images_dir} — skipping")
            continue

        out_img_dir = output_path / split / "images"
        out_mask_dir = output_path / split / "masks"

        split_crop_count = 0
        split_caries_count = 0
        split_no_caries_count = 0
        crop_sizes: list[tuple[int, int]] = []  # (h, w) for average size reporting

        print(f"\nProcessing split: {split} ({len(image_paths)} images)")

        for img_path in image_paths:
            # DC1000 images and masks share the same stem but live in different
            # subdirectories.  We look up the mask by stem to be safe.
            mask_path = masks_dir / img_path.name
            if not mask_path.exists():
                print(f"  WARNING: mask not found for {img_path.name} — skipping")
                continue

            image = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
            assert image is not None, f"failed to read image: {img_path}"

            mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
            assert mask is not None, f"failed to read mask: {mask_path}"

            img_h, img_w = image.shape[:2]
            pano_stem = img_path.stem

            # Run YOLO — verbose=False suppresses per-image console output
            results = model.predict(image, conf=args.conf_threshold, verbose=False)

            # results is a list with one Results object (one image).
            # boxes.xyxy is shape (N, 4) as float32 in pixel coordinates.
            boxes = results[0].boxes.xyxy.cpu().numpy().astype(int)
            confs = results[0].boxes.conf.cpu().numpy()

            for idx, (box, conf) in enumerate(zip(boxes, confs)):
                x1, y1, x2, y2 = box

                bbox_original = (int(x1), int(y1), int(x2), int(y2))
                bbox_padded = add_padding(bbox_original, args.padding, img_h, img_w)

                x1p, y1p, x2p, y2p = bbox_padded
                crop_h = y2p - y1p
                crop_w = x2p - x1p

                # Skip degenerate crops that could arise from extreme padding
                # or near-edge detections collapsing to zero area after clamping.
                if crop_h <= 0 or crop_w <= 0:
                    continue

                filename = f"{pano_stem}_tooth_{idx:03d}.png"

                partial = crop_and_save(
                    image, mask, bbox_padded, out_img_dir, out_mask_dir, filename
                )

                record = {
                    "filename": partial["filename"],
                    "source_image": img_path.name,
                    "split": split,
                    "bbox_original": list(bbox_original),
                    "bbox_padded": partial["bbox_padded"],
                    "confidence": float(conf),
                    "has_caries": partial["has_caries"],
                    "original_size": [img_h, img_w],
                }
                all_metadata.append(record)

                split_crop_count += 1
                crop_sizes.append((crop_h, crop_w))
                if partial["has_caries"]:
                    split_caries_count += 1
                else:
                    split_no_caries_count += 1

        # Compute average crop dimensions before resize — useful to verify
        # that YOLO is producing sensible tooth-sized detections.
        if crop_sizes:
            avg_h = sum(h for h, _ in crop_sizes) / len(crop_sizes)
            avg_w = sum(w for _, w in crop_sizes) / len(crop_sizes)
        else:
            avg_h = avg_w = 0.0

        split_stats[split] = {
            "total_crops": split_crop_count,
            "caries": split_caries_count,
            "non_caries": split_no_caries_count,
            "avg_crop_h": avg_h,
            "avg_crop_w": avg_w,
        }

        print(
            f"  Crops: {split_crop_count}  "
            f"(caries={split_caries_count}, non-caries={split_no_caries_count})  "
            f"avg size={avg_h:.0f}×{avg_w:.0f}px"
        )

    # ------------------------------------------------------------------
    # Write consolidated metadata.json
    # ------------------------------------------------------------------
    metadata_path = output_path / "metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(all_metadata, f, indent=2)
    print(f"\nMetadata written to {metadata_path} ({len(all_metadata)} records)")

    # ------------------------------------------------------------------
    # Create balanced training subset
    #
    # We undersample the majority class in the train split so Stage 2
    # sees equal numbers of caries and non-caries examples, reducing the
    # model's tendency to predict the dominant class.
    # ------------------------------------------------------------------
    balanced_list = create_balanced_split(all_metadata, seed=args.seed)
    balanced_path = output_path / "balanced" / "train_balanced.json"
    with open(balanced_path, "w") as f:
        json.dump(balanced_list, f, indent=2)

    # Confirm the 1:1 ratio held up
    train_meta = {m["filename"]: m for m in all_metadata if m["split"] == "train"}
    balanced_caries = sum(
        1 for fn in balanced_list if train_meta.get(fn, {}).get("has_caries", False)
    )
    balanced_non_caries = len(balanced_list) - balanced_caries
    print(
        f"Balanced train set written to {balanced_path}\n"
        f"  Total: {len(balanced_list)}  "
        f"(caries={balanced_caries}, non-caries={balanced_non_caries})"
    )

    # ------------------------------------------------------------------
    # Summary statistics
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("EXTRACTION SUMMARY")
    print("=" * 60)
    total_crops = sum(s["total_crops"] for s in split_stats.values())
    for split, stats in split_stats.items():
        print(
            f"  {split:6s}  crops={stats['total_crops']:5d}  "
            f"caries={stats['caries']:5d}  "
            f"non-caries={stats['non_caries']:5d}  "
            f"avg_crop={stats['avg_crop_h']:.0f}×{stats['avg_crop_w']:.0f}px"
        )
    print(f"  {'TOTAL':6s}  crops={total_crops:5d}")
    print("=" * 60)


if __name__ == "__main__":
    main()
