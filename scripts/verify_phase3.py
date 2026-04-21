"""Phase 3 Validation: Visual Spot-Check and Balancing Verification
====================================================================

Implements steps 3.3 and 3.4 from the two-stage pipeline plan:

  3.3 — Visual spot-check: overlay 10 random crop masks on crop images and
        save the composites to data/DC1000_cropped/spot_check/.  Pick 5
        caries-positive and 5 caries-negative examples from the train split
        so both categories are represented.

        Overlay scheme:
          • Caries pixels (mask > 127): semi-transparent red fill (alpha 0.4)
            + a full opaque red contour drawn on top.
          • Title bar at the top of each composite shows the filename and
            the caries status so you can sanity-check without needing to
            look up metadata.

  3.4 — Balancing verification: reads train_balanced.json, asserts
        caries == non-caries, and checks every listed filename exists on
        disk.  Exits with a non-zero code if any assertion fails.

Usage::

    # Run both checks (default)
    python scripts/verify_phase3.py

    # Only spot-check
    python scripts/verify_phase3.py --spot-check-only

    # Only balancing verification
    python scripts/verify_phase3.py --balance-only

    # Custom crop root and sample count
    python scripts/verify_phase3.py --crop-path data/DC1000_cropped --n-samples 10 --seed 42
"""

import argparse
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np


# ==============================================================================
# 3.3 — Visual Spot-Check
# ==============================================================================


def draw_mask_overlay(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Compose a visual overlay of the binary mask on top of the BGR image.

    Caries pixels receive a semi-transparent red fill (alpha=0.4) and an
    opaque red contour so the boundary is crisp even on bright radiographs.

    Args:
        image: BGR tooth crop as a numpy array (H, W, 3), any dtype.
        mask: Grayscale mask as a numpy array (H, W), pixel values 0 or 255.

    Returns:
        BGR composite image with the overlay applied, same shape as ``image``.
    """
    # Work on a float copy to blend without clipping artefacts.
    img_f = image.astype(np.float32)
    result = img_f.copy()

    binary = mask > 127  # boolean (H, W)

    if binary.any():
        # Semi-transparent red fill over caries pixels.
        red = np.array([0, 0, 255], dtype=np.float32)  # BGR
        alpha = 0.4
        result[binary] = (1 - alpha) * img_f[binary] + alpha * red

        # Opaque red contour — draw on the uint8 result for crisp edges.
        result_u8 = np.clip(result, 0, 255).astype(np.uint8)
        contours, _ = cv2.findContours(
            binary.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        cv2.drawContours(result_u8, contours, -1, (0, 0, 255), 1)
        return result_u8

    return np.clip(result, 0, 255).astype(np.uint8)


def add_title_bar(image: np.ndarray, title: str) -> np.ndarray:
    """Prepend a black title bar above the image with white text.

    Args:
        image: BGR image to annotate.
        title: Text string to display.

    Returns:
        New image with the title bar prepended (height + 28 pixels).
    """
    bar_h = 28
    bar = np.zeros((bar_h, image.shape[1], 3), dtype=np.uint8)
    cv2.putText(
        bar,
        title,
        (4, 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return np.vstack([bar, image])


def run_spot_check(
    crop_root: Path,
    metadata: list[dict],
    n_samples: int,
    seed: int,
) -> None:
    """Sample n_samples crops (split evenly between caries and non-caries),
    render mask overlays, and save composites to crop_root/spot_check/.

    Args:
        crop_root: Root directory of the cropped dataset.
        metadata: Parsed metadata.json records.
        n_samples: Total number of samples to render (split 50/50 by class).
        seed: Random seed for reproducibility.
    """
    out_dir = crop_root / "spot_check"
    out_dir.mkdir(exist_ok=True)

    # Separate train-split crops by class for balanced sampling.
    # We prefer train crops because they are the most numerous, but fall
    # back to all splits if a class is underrepresented.
    train_caries = [m for m in metadata if m["split"] == "train" and m["has_caries"]]
    train_non_caries = [m for m in metadata if m["split"] == "train" and not m["has_caries"]]

    rng = random.Random(seed)
    half = n_samples // 2

    selected_caries = rng.sample(train_caries, min(half, len(train_caries)))
    selected_non_caries = rng.sample(train_non_caries, min(n_samples - len(selected_caries), len(train_non_caries)))
    selected = selected_caries + selected_non_caries

    print(f"\n[3.3] Visual spot-check: rendering {len(selected)} overlays → {out_dir}")
    failed = 0

    for record in selected:
        split = record["split"]
        filename = record["filename"]
        label = "CARIES" if record["has_caries"] else "no-caries"

        img_path = crop_root / split / "images" / filename
        mask_path = crop_root / split / "masks" / filename

        if not img_path.exists():
            print(f"  WARNING: image not found: {img_path}")
            failed += 1
            continue
        if not mask_path.exists():
            print(f"  WARNING: mask not found: {mask_path}")
            failed += 1
            continue

        image = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)

        if image is None or mask is None:
            print(f"  WARNING: failed to read {filename}")
            failed += 1
            continue

        overlay = draw_mask_overlay(image, mask)
        titled = add_title_bar(overlay, f"{filename}  [{label}]")

        out_path = out_dir / f"overlay_{filename}"
        cv2.imwrite(str(out_path), titled)
        print(f"  saved: {out_path.name}  ({label})")

    if failed:
        print(f"  {failed} file(s) could not be read — review warnings above.")
    else:
        print(f"  All {len(selected)} overlays saved successfully.")
    print(f"  Inspect {out_dir}/ to verify mask alignment and caries visibility.")


# ==============================================================================
# 3.4 — Balancing Verification
# ==============================================================================


def run_balance_verification(crop_root: Path, metadata: list[dict]) -> bool:
    """Verify train_balanced.json has equal class counts and all files exist.

    Args:
        crop_root: Root directory of the cropped dataset.
        metadata: Parsed metadata.json records (used to look up has_caries).

    Returns:
        True if all checks pass, False otherwise.
    """
    balanced_path = crop_root / "balanced" / "train_balanced.json"
    images_dir = crop_root / "train" / "images"
    masks_dir = crop_root / "train" / "masks"

    print(f"\n[3.4] Balancing verification: {balanced_path}")

    if not balanced_path.exists():
        print(f"  ERROR: balanced file not found: {balanced_path}")
        return False

    with open(balanced_path) as f:
        balanced_list: list[str] = json.load(f)

    if not balanced_list:
        print("  ERROR: balanced list is empty.")
        return False

    # Build lookup from filename → has_caries using metadata
    meta_lookup = {m["filename"]: m["has_caries"] for m in metadata if m["split"] == "train"}

    n_caries = 0
    n_non_caries = 0
    missing_images = []
    missing_masks = []
    unknown = []

    for filename in balanced_list:
        if not (images_dir / filename).exists():
            missing_images.append(filename)
        if not (masks_dir / filename).exists():
            missing_masks.append(filename)

        has_caries = meta_lookup.get(filename)
        if has_caries is None:
            unknown.append(filename)
        elif has_caries:
            n_caries += 1
        else:
            n_non_caries += 1

    all_ok = True

    # Report class balance
    print(f"  Total entries : {len(balanced_list)}")
    print(f"  Caries        : {n_caries}")
    print(f"  Non-caries    : {n_non_caries}")

    if n_caries != n_non_caries:
        print(f"  FAIL: class imbalance — caries={n_caries}, non-caries={n_non_caries}")
        all_ok = False
    else:
        print("  PASS: class counts are equal.")

    # Report missing files
    if missing_images:
        print(f"  FAIL: {len(missing_images)} image file(s) listed but missing from disk:")
        for fn in missing_images[:10]:
            print(f"        {fn}")
        if len(missing_images) > 10:
            print(f"        … and {len(missing_images) - 10} more")
        all_ok = False
    else:
        print(f"  PASS: all {len(balanced_list)} image files exist on disk.")

    if missing_masks:
        print(f"  FAIL: {len(missing_masks)} mask file(s) missing:")
        for fn in missing_masks[:10]:
            print(f"        {fn}")
        all_ok = False
    else:
        print(f"  PASS: all {len(balanced_list)} mask files exist on disk.")

    if unknown:
        print(f"  WARN: {len(unknown)} filename(s) not found in metadata (unknown class).")

    return all_ok


# ==============================================================================
# Entry Point
# ==============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 3 validation: spot-check overlays and balance verification."
    )
    parser.add_argument(
        "--crop-path",
        default="data/DC1000_cropped",
        help="Root directory of the cropped tooth dataset (default: data/DC1000_cropped)",
    )
    parser.add_argument(
        "--n-samples",
        type=int,
        default=10,
        help="Number of overlay samples to generate for spot-check (default: 10)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for sample selection (default: 42)",
    )
    parser.add_argument(
        "--spot-check-only",
        action="store_true",
        help="Only run the visual spot-check (skip balancing verification)",
    )
    parser.add_argument(
        "--balance-only",
        action="store_true",
        help="Only run the balancing verification (skip spot-check)",
    )
    args = parser.parse_args()

    crop_root = Path(args.crop_path)
    metadata_path = crop_root / "metadata.json"

    if not crop_root.exists():
        print(f"ERROR: crop directory not found: {crop_root}", file=sys.stderr)
        sys.exit(1)
    if not metadata_path.exists():
        print(f"ERROR: metadata.json not found: {metadata_path}", file=sys.stderr)
        sys.exit(1)

    with open(metadata_path) as f:
        metadata: list[dict] = json.load(f)

    print(f"Loaded metadata: {len(metadata)} records from {metadata_path}")

    checks_passed = True

    if not args.balance_only:
        run_spot_check(crop_root, metadata, args.n_samples, args.seed)

    if not args.spot_check_only:
        ok = run_balance_verification(crop_root, metadata)
        if not ok:
            checks_passed = False

    if not args.spot_check_only:
        if checks_passed:
            print("\nAll Phase 3 validation checks PASSED. Ready for Phase 4.")
        else:
            print("\nOne or more Phase 3 validation checks FAILED. Review output above.")
            sys.exit(1)


if __name__ == "__main__":
    main()
