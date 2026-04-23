"""File I/O helpers for uploads, display copies, and masks.

All paths are rooted at ``settings.STORAGE_ROOT`` and follow the layout::

    uploads/{job_id}/{original_filename}    — raw uploaded image
    display/{image_result_id}.png           — display-resized copy (max 1600 px)
    masks/{image_result_id}.png             — binary caries mask (uint8 {0, 255})

Subdirectories are created on first write.
"""

from __future__ import annotations

import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath

import cv2
import numpy as np

from app.core.config import Settings


class StorageError(RuntimeError):
    """Raised when a file cannot be persisted to storage."""


def _validate_upload_filename(filename: str) -> str:
    """Reject path-like filenames so uploads stay inside the job directory."""
    if filename in {"", ".", ".."}:
        raise ValueError("Uploaded filenames must be non-empty regular file names.")

    posix_path = PurePosixPath(filename)
    windows_path = PureWindowsPath(filename)
    if (
        posix_path.name != filename
        or windows_path.name != filename
        or posix_path.is_absolute()
        or windows_path.is_absolute()
    ):
        raise ValueError("Uploaded filenames must not include directory components.")

    return filename


def _write_png(dest: Path, img: np.ndarray, *, context: str) -> Path:
    """Write a PNG file and fail loudly if OpenCV cannot persist it."""
    ok = cv2.imwrite(str(dest), img)
    if not ok:
        raise StorageError(f"Unable to {context} at {dest}.")
    return dest


# ---------------------------------------------------------------------------
# Upload persistence
# ---------------------------------------------------------------------------


def save_upload(
    content: bytes,
    filename: str,
    job_id: uuid.UUID,
    settings: Settings,
) -> Path:
    """Write raw upload bytes to the storage volume.

    Creates ``{STORAGE_ROOT}/uploads/{job_id}/`` on first call for that job.

    Args:
        content: Raw bytes read from the multipart upload.
        filename: Original filename submitted by the browser; used as-is for
            the on-disk file name.
        job_id: UUID of the parent job; used as the subdirectory name so that
            all uploads for one job are co-located.
        settings: App settings (provides ``STORAGE_ROOT``).

    Returns:
        Absolute path where the file was written.
    """
    safe_filename = _validate_upload_filename(filename)

    upload_dir = settings.STORAGE_ROOT / "uploads" / str(job_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / safe_filename
    try:
        dest.write_bytes(content)
    except OSError as e:
        raise StorageError(f"Unable to save uploaded file at {dest}.") from e
    return dest


# ---------------------------------------------------------------------------
# Display copy
# ---------------------------------------------------------------------------


def save_display_copy(
    img: np.ndarray,
    image_result_id: uuid.UUID,
    settings: Settings,
) -> Path:
    """Resize an image to fit within ``MAX_DISPLAY_PX`` and save as PNG.

    Uses bilinear interpolation.  If both dimensions already fit within the
    limit, the image is saved without resizing.

    Args:
        img: Float32 BGR array in [0, 1] as returned by ``load_image``.
        image_result_id: UUID of the image result row; used as the filename.
        settings: App settings (provides ``STORAGE_ROOT`` and
            ``MAX_DISPLAY_PX``).

    Returns:
        Absolute path of the saved PNG.
    """
    display_dir = settings.STORAGE_ROOT / "display"
    display_dir.mkdir(parents=True, exist_ok=True)

    dest = display_dir / f"{image_result_id}.png"

    h, w = img.shape[:2]
    max_px = settings.MAX_DISPLAY_PX
    if max(h, w) > max_px:
        scale = max_px / max(h, w)
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    # Convert float [0, 1] → uint8 [0, 255] for PNG serialisation.
    img_uint8 = (img * 255).clip(0, 255).astype(np.uint8)
    return _write_png(dest, img_uint8, context="save display copy")


# ---------------------------------------------------------------------------
# Mask persistence
# ---------------------------------------------------------------------------


def save_mask(
    mask: np.ndarray,
    image_result_id: uuid.UUID,
    settings: Settings,
) -> Path:
    """Save a binary mask array as a grayscale PNG.

    Args:
        mask: uint8 array of shape (H, W) with values in {0, 255}.
        image_result_id: UUID of the image result row; used as the filename.
        settings: App settings (provides ``STORAGE_ROOT``).

    Returns:
        Absolute path of the saved PNG.
    """
    mask_dir = settings.STORAGE_ROOT / "masks"
    mask_dir.mkdir(parents=True, exist_ok=True)

    dest = mask_dir / f"{image_result_id}.png"
    return _write_png(dest, mask, context="save mask")
