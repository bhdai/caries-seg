"""
Prepare YOLO Dataset from Tufts Dental Bbox Annotations
=========================================================

Converts the Tufts Dental `teeth_bbox.json` annotation file into
Ultralytics YOLO format and writes a ready-to-train dataset to disk.

Output layout::

    data/tufts_yolo/
      images/train/        # ~800 images (80% split, symlinked from Radiographs/)
      images/val/          # ~200 images (20% split)
      labels/train/        # YOLO txt label files
      labels/val/
      tufts_yolo.yaml      # Ultralytics dataset config

Label format (YOLO normalised, single class "tooth" = 0)::

    0 x_center y_center width height    # all values in [0, 1]

Bbox format in teeth_bbox.json is [top, left, bottom, right] in absolute
pixels. This matches the confirmed assumption that the first coordinate
fits image height (840) and the second fits image width (1615).

Degenerate bboxes (h ≤ min_bbox_size or w ≤ min_bbox_size) are silently
filtered; the final summary prints the count of filtered boxes.
"""

import argparse
import json
import os
import random
import shutil
import sys
from pathlib import Path

import cv2


# ==============================================================================
# Filename Resolution
# ==============================================================================


def resolve_image_path(external_id: str, radiographs_dir: Path) -> Path | None:
    """Resolve a case-insensitive filename from the JSON External ID to the
    actual file path on disk.

    teeth_bbox.json stores External IDs like "797.jpg" while disk files are
    named "797.JPG". We try several case variants before giving up.

    Args:
        external_id: Filename string from the JSON "External ID" field.
        radiographs_dir: Directory containing the .JPG radiograph files.

    Returns:
        Resolved absolute Path if found, None otherwise.
    """
    stem = Path(external_id).stem

    # Common variants: try exact, uppercase extension, lowercase extension
    for ext in (Path(external_id).suffix, ".JPG", ".jpg", ".jpeg", ".JPEG"):
        candidate = radiographs_dir / (stem + ext)
        if candidate.exists():
            return candidate

    return None


# ==============================================================================
# Bbox Conversion
# ==============================================================================


def convert_bbox_to_yolo(
    bbox: list[int], img_h: int, img_w: int, min_size: int
) -> tuple[float, float, float, float] | None:
    """Convert a [top, left, bottom, right] absolute-pixel bbox to YOLO format.

    YOLO format is (x_center, y_center, width, height) with all values
    normalised to [0, 1] relative to the image dimensions.

    Args:
        bbox: [top, left, bottom, right] in absolute pixels.
        img_h: Image height in pixels.
        img_w: Image width in pixels.
        min_size: Minimum allowed bbox height or width. Bboxes smaller than
            this on either axis are considered degenerate and filtered out.

    Returns:
        (x_center, y_center, width, height) normalised tuple, or None if
        the bbox is degenerate.
    """
    top, left, bottom, right = bbox

    bbox_h = bottom - top
    bbox_w = right - left

    if bbox_h <= min_size or bbox_w <= min_size:
        return None

    x_center = (left + right) / 2.0 / img_w
    y_center = (top + bottom) / 2.0 / img_h
    norm_w = bbox_w / img_w
    norm_h = bbox_h / img_h

    return x_center, y_center, norm_w, norm_h


# ==============================================================================
# Entry Point
# ==============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Tufts Dental bbox JSON → Ultralytics YOLO format."
    )
    parser.add_argument(
        "--src",
        default="data/tufts_dental",
        help="Root directory of the Tufts dental dataset (default: data/tufts_dental)",
    )
    parser.add_argument(
        "--dst",
        default="data/tufts_yolo",
        help="Output directory for the YOLO dataset (default: data/tufts_yolo)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for train/val split (default: 42)",
    )
    parser.add_argument(
        "--min-bbox-size",
        type=int,
        default=10,
        dest="min_bbox_size",
        help="Minimum bbox height/width in pixels to keep (default: 10)",
    )
    args = parser.parse_args()

    src = Path(args.src)
    dst = Path(args.dst)
    radiographs_dir = src / "Radiographs"
    bbox_json_path = src / "Segmentation" / "teeth_bbox.json"

    # ------------------------------------------------------------------
    # Validate source paths
    # ------------------------------------------------------------------
    if not radiographs_dir.exists():
        print(f"ERROR: Radiographs directory not found: {radiographs_dir}", file=sys.stderr)
        sys.exit(1)
    if not bbox_json_path.exists():
        print(f"ERROR: teeth_bbox.json not found: {bbox_json_path}", file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Load annotations
    # ------------------------------------------------------------------
    with open(bbox_json_path) as f:
        annotations = json.load(f)

    print(f"Loaded {len(annotations)} annotation entries from {bbox_json_path}")

    # ------------------------------------------------------------------
    # Parse annotations and resolve image paths.
    #
    # We build a list of (image_path, [(x_c, y_c, w, h), ...]) tuples.
    # Images where the file is missing or all bboxes are degenerate are
    # dropped with a logged warning.
    # ------------------------------------------------------------------
    valid_entries: list[tuple[Path, list[tuple[float, float, float, float]]]] = []
    n_filtered = 0
    n_missing = 0

    for entry in annotations:
        external_id = entry.get("External ID", "")
        image_path = resolve_image_path(external_id, radiographs_dir)

        if image_path is None:
            print(f"  WARNING: image not found for External ID '{external_id}' — skipping")
            n_missing += 1
            continue

        # Read image dimensions to normalise bbox coordinates.
        # We use IMREAD_UNCHANGED (fastest) — we only need shape.
        img = cv2.imread(str(image_path))
        if img is None:
            print(f"  WARNING: could not read image {image_path} — skipping")
            n_missing += 1
            continue
        img_h, img_w = img.shape[:2]

        # Convert every bbox annotation for this image
        label_lines: list[tuple[float, float, float, float]] = []
        for obj in entry.get("Label", {}).get("objects", []):
            bbox = obj.get("bounding box")
            if bbox is None:
                continue
            yolo_bbox = convert_bbox_to_yolo(bbox, img_h, img_w, args.min_bbox_size)
            if yolo_bbox is None:
                n_filtered += 1
                continue
            label_lines.append(yolo_bbox)

        # Only keep images that have at least one valid bbox
        if label_lines:
            valid_entries.append((image_path, label_lines))

    print(f"Images with at least one valid bbox: {len(valid_entries)}")
    print(f"Bboxes filtered (degenerate, h or w ≤ {args.min_bbox_size}px): {n_filtered}")
    print(f"Images skipped (file not found or unreadable): {n_missing}")

    # ------------------------------------------------------------------
    # 80/20 train/val split — random shuffle with fixed seed
    # ------------------------------------------------------------------
    rng = random.Random(args.seed)
    indices = list(range(len(valid_entries)))
    rng.shuffle(indices)

    split_idx = int(len(indices) * 0.8)
    train_indices = indices[:split_idx]
    val_indices = indices[split_idx:]

    print(f"Train images: {len(train_indices)}, Val images: {len(val_indices)}")

    # ------------------------------------------------------------------
    # Create output directory structure
    # ------------------------------------------------------------------
    for subdir in (
        "images/train", "images/val",
        "labels/train", "labels/val",
    ):
        (dst / subdir).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Write images and labels for each split
    # ------------------------------------------------------------------
    def write_split(idx_list: list[int], split_name: str) -> int:
        """Copy images and write YOLO label files for the given split.

        Returns the total number of bbox lines written across all images.
        """
        total_labels = 0
        for i in idx_list:
            img_path, label_lines = valid_entries[i]

            # Copy image into the split folder
            dst_img = dst / "images" / split_name / img_path.name
            shutil.copy2(img_path, dst_img)

            # Write label file — one line per bbox: "0 xc yc w h"
            label_stem = img_path.stem
            dst_label = dst / "labels" / split_name / f"{label_stem}.txt"
            with open(dst_label, "w") as lf:
                for xc, yc, w, h in label_lines:
                    lf.write(f"0 {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")
                    total_labels += 1

        return total_labels

    train_labels = write_split(train_indices, "train")
    val_labels = write_split(val_indices, "val")

    print(f"Labels written — train: {train_labels}, val: {val_labels}, total: {train_labels + val_labels}")

    # ------------------------------------------------------------------
    # Write tufts_yolo.yaml dataset config
    # ------------------------------------------------------------------
    # Ultralytics expects absolute paths in the YAML so it can find the
    # data regardless of the working directory at train time.
    abs_dst = dst.resolve()
    yaml_path = dst / "tufts_yolo.yaml"
    yaml_content = (
        f"path: {abs_dst}\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"\n"
        f"nc: 1\n"
        f"names:\n"
        f"  0: tooth\n"
    )
    yaml_path.write_text(yaml_content)
    print(f"Dataset config written to {yaml_path}")

    # ------------------------------------------------------------------
    # Visual sanity-check: save 5 annotated sample images
    #
    # Each image shows detected bboxes drawn on the radiograph so we can
    # visually confirm the bbox coordinate interpretation is correct before
    # kicking off YOLO training.
    # ------------------------------------------------------------------
    sample_dir = dst / "samples"
    sample_dir.mkdir(exist_ok=True)

    # Pick 5 random entries from the train split for variety
    sample_indices = rng.sample(train_indices, min(5, len(train_indices)))
    for i in sample_indices:
        img_path, label_lines = valid_entries[i]
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        h, w = img.shape[:2]

        for xc, yc, bw, bh in label_lines:
            # Convert back to absolute pixel coords for drawing
            x1 = int((xc - bw / 2) * w)
            y1 = int((yc - bh / 2) * h)
            x2 = int((xc + bw / 2) * w)
            y2 = int((yc + bh / 2) * h)
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)

        out_path = sample_dir / f"annotated_{img_path.stem}.jpg"
        cv2.imwrite(str(out_path), img)

    print(f"5 annotated sample images saved to {sample_dir}/")
    print("Done. Visually inspect samples/ before starting YOLO training.")


if __name__ == "__main__":
    main()
