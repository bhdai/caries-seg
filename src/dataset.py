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
