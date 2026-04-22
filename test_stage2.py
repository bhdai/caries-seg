"""
Test Script — Stage 2 Caries Segmentation Evaluation
======================================================

Two evaluation modes:

Mode A — Tooth-level (default):
    Iterates over data/DC1000_cropped/test/ crops one by one.
    Computes the 7-metric suite (Jaccard, F1, Recall, Precision, Acc, F2, HD).
    Reports mean metrics across all test crops.
    Optional --save-preds saves predicted masks and side-by-side visualisations.

Mode B — Panoramic reconstruction (--panoramic flag):
    Reads metadata.json to get bbox coordinates per crop.
    For each test panoramic image:
      - Creates a blank full-size mask (H×W of original).
      - For each crop belonging to that panoramic, runs Stage 2 inference,
        resizes prediction to padded-bbox dimensions, and pastes it into the
        canvas using logical OR for overlapping regions.
    Compares reconstructed full mask against DC1000 ground truth.
    Reports mean metrics across all test panoramic images.
    Optional --save-preds saves reconstructed panoramic predictions + overlays.
"""

import argparse
import datetime
import json
import os
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import torch

from src.dataset import load_cropped_data
from src.metrics import calculate_metrics
from src.models import AttentionUNet, DoubleUnet, UNet
from src.utils import create_dir, print_and_save, seeding


# ==============================================================================
# Model Registry
# ==============================================================================

MODEL_REGISTRY: dict[str, type] = {
    "UNet": UNet,
    "DoubleUnet": DoubleUnet,
    "AttentionUNet": AttentionUNet,
}


# ==============================================================================
# Shared Helpers
# ==============================================================================


def load_state_dict(checkpoint_path: str, device: torch.device) -> dict:
    """Load checkpoint with graceful fallback for older PyTorch versions."""
    try:
        return torch.load(checkpoint_path, map_location=device, weights_only=True)
    except TypeError:
        return torch.load(checkpoint_path, map_location=device)


def preprocess_crop(
    image_path: str,
    size: int,
    device: torch.device,
) -> torch.Tensor:
    """Load a crop image, resize, normalise, and move to device.

    Returns:
        Float32 tensor of shape (1, 3, size, size) in [0, 1].
    """
    image = cv2.imread(image_path, cv2.IMREAD_COLOR)
    assert image is not None, f"failed to read image: {image_path}"
    image = cv2.resize(image, (size, size), interpolation=cv2.INTER_LINEAR)
    image = np.transpose(image, (2, 0, 1)).astype(np.float32) / 255.0
    return torch.from_numpy(image[np.newaxis]).to(device, dtype=torch.float32)


def prediction_to_rgb(pred: np.ndarray) -> np.ndarray:
    """Convert a binary 2-D prediction array (0/1) to a 3-channel uint8 image."""
    binary = (pred > 0).astype(np.uint8) * 255
    return np.repeat(binary[..., np.newaxis], 3, axis=2)


def save_crop_artifacts(
    save_dir: str,
    image_path: str,
    original_image: np.ndarray,
    original_mask: np.ndarray,
    prediction_rgb: np.ndarray,
) -> None:
    """Save predicted mask and side-by-side joint image for a single crop."""
    height, width = original_mask.shape
    pred_resized = cv2.resize(
        prediction_rgb, (width, height), interpolation=cv2.INTER_NEAREST
    )
    mask_rgb = np.repeat(original_mask[..., np.newaxis], 3, axis=2)
    separator = np.full((height, 10, 3), 255, dtype=np.uint8)
    joint = np.concatenate(
        [original_image, separator, mask_rgb, separator, pred_resized], axis=1
    )

    filename = os.path.basename(image_path)
    cv2.imwrite(os.path.join(save_dir, "pred", filename), pred_resized)
    cv2.imwrite(os.path.join(save_dir, "joint", filename), joint)


# ==============================================================================
# Mode A — Tooth-level Evaluation
# ==============================================================================


@torch.no_grad()
def evaluate_tooth_level(
    model: torch.nn.Module,
    crop_dir: str,
    image_size: int,
    device: torch.device,
    save_dir: str | None = None,
) -> dict[str, float]:
    """Evaluate model on individual tooth crops from the test split.

    Iterates over every (image, mask) pair in ``{crop_dir}/test/``, runs
    inference, and accumulates the 7-metric suite.

    Args:
        model: Loaded, eval-mode segmentation model.
        crop_dir: Root of the cropped dataset (e.g. ``data/DC1000_cropped``).
        image_size: Resize dimension (square); must match training size.
        device: Torch device.
        save_dir: If provided, saves predicted masks and joint visualisations here.

    Returns:
        Dict with keys: jaccard, f1, recall, precision, accuracy, f2, hausdorff.
    """
    (_, _), (_, _), (test_x, test_y) = load_cropped_data(crop_dir, balanced=False)
    assert test_x, f"No test crops found in {crop_dir}/test/images/"

    total_metrics = np.zeros(7, dtype=np.float64)
    inference_times: list[float] = []

    for image_path, mask_path in zip(test_x, test_y):
        # --- Load crop and mask ---
        image_t = preprocess_crop(image_path, image_size, device)

        mask_raw = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        assert mask_raw is not None, f"failed to read mask: {mask_path}"
        mask_resized = cv2.resize(
            mask_raw, (image_size, image_size), interpolation=cv2.INTER_NEAREST
        )
        mask_bin = (mask_resized > 127).astype(np.float32)
        mask_t = torch.from_numpy(mask_bin[np.newaxis, np.newaxis]).to(
            device, dtype=torch.float32
        )

        # --- Inference ---
        t0 = time.time()
        out = model({"images": image_t, "masks": mask_t})
        y_pred = torch.sigmoid(out["prediction"])
        inference_times.append(time.time() - t0)

        total_metrics += np.asarray(
            calculate_metrics(mask_t, y_pred), dtype=np.float64
        )

        # --- Optional save ---
        if save_dir is not None:
            original_image = cv2.imread(image_path, cv2.IMREAD_COLOR)
            pred_np = (y_pred[0, 0].cpu().numpy() > 0.5)
            save_crop_artifacts(
                save_dir,
                image_path,
                original_image,
                mask_raw,
                prediction_to_rgb(pred_np),
            )

    n = len(test_x)
    avg = total_metrics / n
    mean_t = float(np.mean(inference_times))

    return {
        "n_samples": n,
        "jaccard": avg[0],
        "f1": avg[1],
        "recall": avg[2],
        "precision": avg[3],
        "accuracy": avg[4],
        "f2": avg[5],
        "hausdorff": avg[6],
        "mean_inference_time": mean_t,
        "fps": 1.0 / mean_t if mean_t > 0 else 0.0,
    }


# ==============================================================================
# Mode B — Panoramic Reconstruction Evaluation
# ==============================================================================


@torch.no_grad()
def reconstruct_panoramic_mask(
    model: torch.nn.Module,
    crops_for_image: list[dict],
    crop_images_dir: str,
    original_h: int,
    original_w: int,
    image_size: int,
    device: torch.device,
) -> np.ndarray:
    """Reconstruct a full panoramic caries mask from individual tooth predictions.

    For each crop belonging to the given panoramic:
      1. Run Stage 2 inference → binary prediction at ``image_size × image_size``.
      2. Resize prediction back to the padded-bbox spatial dimensions.
      3. Paste into a full-size blank canvas using logical OR (union) for overlaps.

    Args:
        model: Loaded, eval-mode segmentation model.
        crops_for_image: List of metadata dicts for crops belonging to this image.
        crop_images_dir: Path to the ``images/`` directory for this split.
        original_h: Height of the original panoramic image (pixels).
        original_w: Width of the original panoramic image (pixels).
        image_size: Inference resize dimension (square).
        device: Torch device.

    Returns:
        Reconstructed binary mask of shape ``(original_h, original_w)``, dtype uint8,
        values 0 or 255.
    """
    pred_full = np.zeros((original_h, original_w), dtype=np.uint8)

    for crop_meta in crops_for_image:
        crop_image_path = os.path.join(crop_images_dir, crop_meta["filename"])
        if not os.path.exists(crop_image_path):
            # Log but don't crash — crop may have been filtered for another reason.
            print(f"  [warn] crop not found on disk: {crop_image_path}")
            continue

        # Inference
        image_t = preprocess_crop(crop_image_path, image_size, device)
        out = model({"images": image_t})
        pred = torch.sigmoid(out["prediction"])[0, 0].cpu().numpy()  # (H, W)
        pred_bin = (pred > 0.5).astype(np.uint8)

        # Resize prediction to original padded-bbox dimensions
        x1, y1, x2, y2 = crop_meta["bbox_padded"]
        target_w = max(1, x2 - x1)
        target_h = max(1, y2 - y1)
        pred_resized = cv2.resize(
            pred_bin, (target_w, target_h), interpolation=cv2.INTER_NEAREST
        )

        # Paste with logical OR (union) to handle overlapping detections
        pred_full[y1:y2, x1:x2] = np.maximum(
            pred_full[y1:y2, x1:x2], pred_resized * 255
        )

    return pred_full


@torch.no_grad()
def evaluate_panoramic_level(
    model: torch.nn.Module,
    metadata_path: str,
    dc1000_path: str,
    crop_dir: str,
    image_size: int,
    device: torch.device,
    save_dir: str | None = None,
) -> dict[str, float]:
    """Evaluate reconstructed panoramic masks against DC1000 ground truth.

    Groups test-split crops by their source panoramic image, reconstructs
    full-size prediction masks, and computes the 7-metric suite against the
    original DC1000 binary GT masks.

    Args:
        model: Loaded, eval-mode segmentation model.
        metadata_path: Path to ``metadata.json`` written by extract_tooth_crops.py.
        dc1000_path: Root of DC1000 dataset (e.g. ``data/DC1000``).
        crop_dir: Root of the cropped dataset (for crop image paths).
        image_size: Inference resize dimension (square).
        device: Torch device.
        save_dir: If provided, saves reconstructed panoramic masks and overlays.

    Returns:
        Dict with keys: jaccard, f1, recall, precision, accuracy, f2, hausdorff,
        n_panoramics, n_empty (panoramics with 0 detected crops).
    """
    assert os.path.exists(metadata_path), (
        f"metadata.json not found: {metadata_path}\n"
        "Run scripts/extract_tooth_crops.py first."
    )
    with open(metadata_path) as f:
        metadata: list[dict] = json.load(f)

    # Group crops by (split, source_image)
    crops_by_pano: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for record in metadata:
        crops_by_pano[(record["split"], record["source_image"])].append(record)

    # Collect test panoramic GT mask paths
    test_mask_dir = os.path.join(dc1000_path, "test", "masks")
    test_image_dir = os.path.join(dc1000_path, "test", "images")
    assert os.path.isdir(test_mask_dir), f"DC1000 test mask dir not found: {test_mask_dir}"

    gt_mask_paths = sorted(Path(test_mask_dir).glob("*.png"))
    assert gt_mask_paths, f"No GT masks found in {test_mask_dir}"

    crop_test_images_dir = os.path.join(crop_dir, "test", "images")

    total_metrics = np.zeros(7, dtype=np.float64)
    n_empty = 0
    inference_times: list[float] = []

    for gt_mask_path in gt_mask_paths:
        pano_name = gt_mask_path.name

        gt_mask = cv2.imread(str(gt_mask_path), cv2.IMREAD_GRAYSCALE)
        assert gt_mask is not None, f"failed to read GT mask: {gt_mask_path}"
        img_h, img_w = gt_mask.shape

        crops = crops_by_pano.get(("test", pano_name), [])
        if not crops:
            n_empty += 1
            print(f"  [warn] no crops for panoramic: {pano_name} — using all-zero prediction")

        t0 = time.time()
        pred_full = reconstruct_panoramic_mask(
            model=model,
            crops_for_image=crops,
            crop_images_dir=crop_test_images_dir,
            original_h=img_h,
            original_w=img_w,
            image_size=image_size,
            device=device,
        )
        inference_times.append(time.time() - t0)

        # Convert to tensors for unified metric calculation
        gt_bin = (gt_mask > 127).astype(np.float32)
        pred_bin = (pred_full > 127).astype(np.float32)

        gt_t = torch.from_numpy(gt_bin[np.newaxis, np.newaxis]).to(device)
        pred_t = torch.from_numpy(pred_bin[np.newaxis, np.newaxis]).to(device)

        total_metrics += np.asarray(
            calculate_metrics(gt_t, pred_t), dtype=np.float64
        )

        # --- Optional save ---
        if save_dir is not None:
            pano_image_path = os.path.join(test_image_dir, pano_name)
            original_image = cv2.imread(pano_image_path, cv2.IMREAD_COLOR)
            if original_image is not None:
                # Side-by-side: original | GT | prediction
                gt_rgb = np.repeat(gt_mask[..., np.newaxis], 3, axis=2)
                pred_rgb = prediction_to_rgb(pred_bin)
                sep = np.full((img_h, 10, 3), 255, dtype=np.uint8)
                joint = np.concatenate(
                    [original_image, sep, gt_rgb, sep, pred_rgb], axis=1
                )
                cv2.imwrite(os.path.join(save_dir, "pred", pano_name), pred_full)
                cv2.imwrite(os.path.join(save_dir, "joint", pano_name), joint)

    n = len(gt_mask_paths)
    avg = total_metrics / n
    mean_t = float(np.mean(inference_times))

    return {
        "n_panoramics": n,
        "n_empty": n_empty,
        "jaccard": avg[0],
        "f1": avg[1],
        "recall": avg[2],
        "precision": avg[3],
        "accuracy": avg[4],
        "f2": avg[5],
        "hausdorff": avg[6],
        "mean_inference_time": mean_t,
        "fps": 1.0 / mean_t if mean_t > 0 else 0.0,
    }


# ==============================================================================
# Main
# ==============================================================================


def main() -> None:
    seeding(42)

    parser = argparse.ArgumentParser(
        description="Evaluate a Stage 2 segmentation model at tooth-level and/or panoramic-level"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="AttentionUNet",
        choices=list(MODEL_REGISTRY.keys()),
        help="Model architecture (default: AttentionUNet)",
    )
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=None,
        help="Path to checkpoint .pth (default: files/stage2_{model}/checkpoint.pth)",
    )
    parser.add_argument(
        "--data_path",
        type=str,
        default="data/DC1000_cropped",
        help="Root of the cropped tooth dataset (default: data/DC1000_cropped)",
    )
    parser.add_argument(
        "--dc1000_path",
        type=str,
        default="data/DC1000",
        help="Root of DC1000 dataset, used for panoramic GT masks (default: data/DC1000)",
    )
    parser.add_argument(
        "--image_size",
        type=int,
        default=256,
        help="Square inference resize dimension (default: 256)",
    )
    parser.add_argument(
        "--panoramic",
        action="store_true",
        help="Run panoramic reconstruction evaluation (Mode B) in addition to tooth-level",
    )
    parser.add_argument(
        "--save-preds",
        action="store_true",
        help="Save predicted masks and side-by-side visualisations",
    )
    parser.add_argument(
        "--save-dir",
        type=str,
        default=None,
        help="Directory for saved predictions (default: files/stage2_{model}/result_map)",
    )
    opt = parser.parse_args()

    # ----- paths -----
    file_path = f"files/stage2_{opt.model}"
    create_dir(file_path)

    checkpoint_path = opt.checkpoint or f"{file_path}/checkpoint.pth"
    if not os.path.exists(checkpoint_path):
        raise FileNotFoundError(
            f"Checkpoint not found: {checkpoint_path}\n"
            f"Train first with: python train_stage2.py --model {opt.model}"
        )

    test_log_path = f"{file_path}/test_log.txt"
    if not os.path.exists(test_log_path):
        with open(test_log_path, "w") as f:
            f.write("\n")

    print_and_save(test_log_path, str(datetime.datetime.now()))
    print_and_save(test_log_path, f"Model: {opt.model}")
    print_and_save(test_log_path, f"Checkpoint: {checkpoint_path}")
    print_and_save(test_log_path, f"Image size: {opt.image_size}")

    # ----- optional save directory -----
    save_dir = None
    if opt.save_preds:
        save_dir = opt.save_dir or f"{file_path}/result_map"
        create_dir(save_dir)
        create_dir(os.path.join(save_dir, "pred"))
        create_dir(os.path.join(save_dir, "joint"))
        print_and_save(test_log_path, f"Saving predictions to: {save_dir}")

    # ----- model -----
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model_cls = MODEL_REGISTRY[opt.model]
    model = model_cls().to(device)
    model.load_state_dict(load_state_dict(checkpoint_path, device))
    model.eval()
    print_and_save(test_log_path, f"Device: {device}\n")

    # ==================================================================
    # Mode A — Tooth-level Evaluation
    # ==================================================================
    print_and_save(test_log_path, "=" * 60)
    print_and_save(test_log_path, "Mode A — Tooth-level Evaluation")
    print_and_save(test_log_path, "=" * 60)

    tooth_results = evaluate_tooth_level(
        model=model,
        crop_dir=opt.data_path,
        image_size=opt.image_size,
        device=device,
        save_dir=save_dir,
    )

    tooth_str = (
        f"Samples: {tooth_results['n_samples']}\n"
        f"Jaccard:   {tooth_results['jaccard']:.4f}\n"
        f"F1:        {tooth_results['f1']:.4f}\n"
        f"Recall:    {tooth_results['recall']:.4f}\n"
        f"Precision: {tooth_results['precision']:.4f}\n"
        f"Accuracy:  {tooth_results['accuracy']:.4f}\n"
        f"F2:        {tooth_results['f2']:.4f}\n"
        f"Hausdorff: {tooth_results['hausdorff']:.4f}\n"
        f"Mean inference time: {tooth_results['mean_inference_time']:.4f}s "
        f"({tooth_results['fps']:.1f} FPS)\n"
    )
    print_and_save(test_log_path, tooth_str)

    # ==================================================================
    # Mode B — Panoramic Reconstruction Evaluation (optional)
    # ==================================================================
    if opt.panoramic:
        metadata_path = os.path.join(opt.data_path, "metadata.json")

        # Use a separate save_dir subdirectory for panoramic outputs.
        pano_save_dir = None
        if save_dir is not None:
            pano_save_dir = os.path.join(save_dir, "panoramic")
            create_dir(pano_save_dir)
            create_dir(os.path.join(pano_save_dir, "pred"))
            create_dir(os.path.join(pano_save_dir, "joint"))

        print_and_save(test_log_path, "=" * 60)
        print_and_save(test_log_path, "Mode B — Panoramic Reconstruction Evaluation")
        print_and_save(test_log_path, "=" * 60)

        pano_results = evaluate_panoramic_level(
            model=model,
            metadata_path=metadata_path,
            dc1000_path=opt.dc1000_path,
            crop_dir=opt.data_path,
            image_size=opt.image_size,
            device=device,
            save_dir=pano_save_dir,
        )

        pano_str = (
            f"Panoramics: {pano_results['n_panoramics']} "
            f"({pano_results['n_empty']} with no detected crops)\n"
            f"Jaccard:   {pano_results['jaccard']:.4f}\n"
            f"F1:        {pano_results['f1']:.4f}\n"
            f"Recall:    {pano_results['recall']:.4f}\n"
            f"Precision: {pano_results['precision']:.4f}\n"
            f"Accuracy:  {pano_results['accuracy']:.4f}\n"
            f"F2:        {pano_results['f2']:.4f}\n"
            f"Hausdorff: {pano_results['hausdorff']:.4f}\n"
            f"Mean inference time per panoramic: {pano_results['mean_inference_time']:.4f}s "
            f"({pano_results['fps']:.2f} panoramics/s)\n"
        )
        print_and_save(test_log_path, pano_str)


if __name__ == "__main__":
    main()
