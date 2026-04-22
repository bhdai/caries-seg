import json
import os
from glob import glob

import cv2
import numpy as np
from torch.utils.data import Dataset


def load_DC1000_data(path: str):
    """Load image/mask paths for train, valid, and test splits.

    Expects directory layout::

        path/
          train/images/*.png  train/masks/*.png
          valid/images/*.png  valid/masks/*.png
          test/images/*.png   test/masks/*.png

    Returns [(train_x, train_y), (valid_x, valid_y), (test_x, test_y)].
    """

    def get_data(split_path: str):
        images = sorted(glob(os.path.join(split_path, "images", "*.png")))
        labels = sorted(glob(os.path.join(split_path, "masks", "*.png")))
        assert len(images) == len(labels), (
            f"image/mask count mismatch in {split_path}: {len(images)} vs {len(labels)}"
        )
        return images, labels

    train_x, train_y = get_data(os.path.join(path, "train"))
    valid_x, valid_y = get_data(os.path.join(path, "valid"))
    test_x, test_y = get_data(os.path.join(path, "test"))

    return [(train_x, train_y), (valid_x, valid_y), (test_x, test_y)]


class DC1000Dataset(Dataset):
    """Dataset for the DC1000 dental caries segmentation benchmark.

    Loads panoramic radiograph images and binary masks, resizes to
    ``size``, normalises images to [0, 1], and binarises masks at 127.
    """

    def __init__(
        self,
        images_path: list[str],
        masks_path: list[str],
        size: tuple[int, int],
        transform=None,
    ):
        super().__init__()
        self.images_path = images_path
        self.masks_path = masks_path
        self.size = size
        self.transform = transform
        self.n_samples = len(images_path)

    def __getitem__(self, index: int):
        image = cv2.imread(self.images_path[index], cv2.IMREAD_COLOR)
        assert image is not None, f"failed to read image: {self.images_path[index]}"
        mask = cv2.imread(self.masks_path[index], cv2.IMREAD_GRAYSCALE)
        assert mask is not None, f"failed to read mask: {self.masks_path[index]}"

        if self.transform is not None:
            augmentations = self.transform(image=image, mask=mask)
            image = augmentations["image"]
            mask = augmentations["mask"]

        image = cv2.resize(image, self.size, interpolation=cv2.INTER_NEAREST)
        image = np.transpose(image, (2, 0, 1))  # HWC → CHW
        image = image.astype(np.float32) / 255.0

        mask = cv2.resize(mask, self.size, interpolation=cv2.INTER_NEAREST)
        mask = (mask > 127).astype(np.float32)
        mask = np.expand_dims(mask, axis=0)  # 1×H×W

        return image, mask

    def __len__(self) -> int:
        return self.n_samples


# ==============================================================================
# Stage 2 — Cropped Tooth Dataset
# ==============================================================================


def load_cropped_data(
    path: str,
    balanced: bool = False,
) -> tuple[
    tuple[list[str], list[str]],
    tuple[list[str], list[str]],
    tuple[list[str], list[str]],
]:
    """Load cropped tooth dataset file paths from a DC1000_cropped directory.

    Expects the same split layout as DC1000 (train / valid / test), each with
    ``images/`` and ``masks/`` subdirectories containing ``*.png`` files.

    If *balanced* is True, the train split is filtered to only the filenames
    listed in ``balanced/train_balanced.json`` (written by
    ``scripts/extract_tooth_crops.py``).

    Args:
        path: Root directory of the cropped dataset (e.g. ``data/DC1000_cropped``).
        balanced: When True, restrict the train split to the pre-computed
            balanced subset (1:1 caries / non-caries ratio).

    Returns:
        Three ``(images, masks)`` path-list tuples for train, valid, and test.
    """

    def _get_split(split_path: str) -> tuple[list[str], list[str]]:
        images = sorted(glob(os.path.join(split_path, "images", "*.png")))
        masks = sorted(glob(os.path.join(split_path, "masks", "*.png")))
        assert len(images) == len(masks), (
            f"image/mask count mismatch in {split_path}: "
            f"{len(images)} images vs {len(masks)} masks"
        )
        return images, masks

    train_x, train_y = _get_split(os.path.join(path, "train"))
    valid_x, valid_y = _get_split(os.path.join(path, "valid"))
    test_x, test_y = _get_split(os.path.join(path, "test"))

    # ------------------------------------------------------------------
    # Optional: filter train split to balanced subset
    # ------------------------------------------------------------------
    if balanced:
        balanced_json = os.path.join(path, "balanced", "train_balanced.json")
        assert os.path.exists(balanced_json), (
            f"balanced/train_balanced.json not found at {balanced_json}; "
            "run scripts/extract_tooth_crops.py first"
        )
        with open(balanced_json) as f:
            allowed: set[str] = set(json.load(f))

        # Keep only paths whose basename is in the allowed set.
        train_pairs = [
            (img, msk)
            for img, msk in zip(train_x, train_y)
            if os.path.basename(img) in allowed
        ]
        assert train_pairs, (
            "balanced filter removed all training samples — "
            "check that train_balanced.json filenames match the images/ directory"
        )
        train_x, train_y = zip(*train_pairs)
        train_x, train_y = list(train_x), list(train_y)

    return (train_x, train_y), (valid_x, valid_y), (test_x, test_y)


class CroppedToothDataset(Dataset):
    """Dataset for individual tooth crops and their caries segmentation masks.

    Designed for Stage 2 training on the DC1000_cropped dataset produced by
    ``scripts/extract_tooth_crops.py``.  Behaviour is identical to
    :class:`DC1000Dataset` but defaults to 256×256 to match the smaller
    crop input size used in Stage 2.

    Args:
        images: Absolute paths to crop images (BGR PNG files).
        masks: Absolute paths to crop masks (grayscale PNG files).
        size: Target spatial resolution for both image and mask (square).
        transform: Optional Albumentations transform applied **before**
            resize, consistent with the existing pipeline convention.

    Yields:
        ``(image, mask)`` where *image* is ``float32 CHW [0, 1]`` and
        *mask* is ``float32 1HW`` binary (0 or 1).
    """

    def __init__(
        self,
        images: list[str],
        masks: list[str],
        size: int = 256,
        transform=None,
    ) -> None:
        super().__init__()
        self.images_path = images
        self.masks_path = masks
        # Store as (W, H) tuple for cv2.resize, which takes (width, height).
        self._cv2_size = (size, size)
        self.transform = transform
        self.n_samples = len(images)

    def __getitem__(self, index: int) -> tuple[np.ndarray, np.ndarray]:
        image = cv2.imread(self.images_path[index], cv2.IMREAD_COLOR)
        assert image is not None, f"failed to read image: {self.images_path[index]}"
        mask = cv2.imread(self.masks_path[index], cv2.IMREAD_GRAYSCALE)
        assert mask is not None, f"failed to read mask: {self.masks_path[index]}"

        if self.transform is not None:
            augmented = self.transform(image=image, mask=mask)
            image = augmented["image"]
            mask = augmented["mask"]

        image = cv2.resize(image, self._cv2_size, interpolation=cv2.INTER_LINEAR)
        image = np.transpose(image, (2, 0, 1))   # HWC → CHW
        image = image.astype(np.float32) / 255.0

        mask = cv2.resize(mask, self._cv2_size, interpolation=cv2.INTER_NEAREST)
        mask = (mask > 127).astype(np.float32)
        mask = np.expand_dims(mask, axis=0)       # 1×H×W

        return image, mask

    def __len__(self) -> int:
        return self.n_samples
