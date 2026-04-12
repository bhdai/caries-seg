"""
Data Preparation Script — DC1000 Dataset Split
================================================

Reads panorama images from org_train_dataset and org_test_dataset,
verifies image-label pairing, splits train data 80/20 into train/valid,
and physically copies files into the DC1000/{train,valid,test}/{images,masks}/
directory structure expected by the training pipeline.

Original data in org_train_dataset and org_test_dataset is never modified.
"""

import os
import shutil
import random
from pathlib import Path


def get_matched_pairs(image_dir: Path, label_dir: Path) -> list[tuple[Path, Path]]:
    """Return sorted list of (image, label) path pairs where both files exist."""
    image_files = {f.name: f for f in image_dir.iterdir() if f.suffix == ".png"}
    label_files = {f.name: f for f in label_dir.iterdir() if f.suffix == ".png"}

    matched = []
    skipped = []
    for name in sorted(image_files.keys()):
        if name in label_files:
            matched.append((image_files[name], label_files[name]))
        else:
            skipped.append(name)

    if skipped:
        print(f"WARNING: {len(skipped)} images have no matching label — skipped: {skipped}")

    return matched


def copy_pairs_to_dir(pairs: list[tuple[Path, Path]], target_dir: Path) -> None:
    """Copy image-label pairs into target_dir/{images,masks}/."""
    images_dir = target_dir / "images"
    masks_dir = target_dir / "masks"
    images_dir.mkdir(parents=True, exist_ok=True)
    masks_dir.mkdir(parents=True, exist_ok=True)

    for img_path, lbl_path in pairs:
        shutil.copy2(img_path, images_dir / img_path.name)
        shutil.copy2(lbl_path, masks_dir / lbl_path.name)


def main():
    seed = 42
    val_ratio = 0.2

    # ==============================================================================
    # Paths
    # ==============================================================================

    project_root = Path(__file__).resolve().parent.parent
    data_root = project_root / "data" / "DC1000_dataset"

    org_train_images = data_root / "org_train_dataset" / "images"
    org_train_labels = data_root / "org_train_dataset" / "labels_clean"
    org_test_images = data_root / "org_test_dataset" / "images"
    org_test_labels = data_root / "org_test_dataset" / "labels"

    output_root = project_root / "data" / "DC1000"

    # Clean stale output to prevent contamination from prior runs.
    if output_root.exists():
        import shutil as _shutil
        _shutil.rmtree(output_root)
        print(f"Removed stale output directory: {output_root}")

    # ==============================================================================
    # Match and shuffle train pairs
    # ==============================================================================

    train_pairs = get_matched_pairs(org_train_images, org_train_labels)
    print(f"Matched train pairs: {len(train_pairs)}")

    random.seed(seed)
    random.shuffle(train_pairs)

    # ==============================================================================
    # Split 80/20
    # ==============================================================================

    split_idx = int(len(train_pairs) * (1 - val_ratio))
    train_split = train_pairs[:split_idx]
    valid_split = train_pairs[split_idx:]

    print(f"Train split: {len(train_split)}")
    print(f"Valid split: {len(valid_split)}")

    # ==============================================================================
    # Copy train and valid splits
    # ==============================================================================

    copy_pairs_to_dir(train_split, output_root / "train")
    copy_pairs_to_dir(valid_split, output_root / "valid")

    # ==============================================================================
    # Copy test set
    # ==============================================================================

    test_pairs = get_matched_pairs(org_test_images, org_test_labels)
    print(f"Test pairs: {len(test_pairs)}")
    copy_pairs_to_dir(test_pairs, output_root / "test")

    print(f"\nData prepared at: {output_root}")
    print(f"  train: {len(train_split)} pairs")
    print(f"  valid: {len(valid_split)} pairs")
    print(f"  test:  {len(test_pairs)} pairs")


if __name__ == "__main__":
    main()
