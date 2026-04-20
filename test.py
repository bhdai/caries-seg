"""
Test Script — DC1000 Held-Out Evaluation
========================================

Loads a saved segmentation checkpoint, evaluates it on the DC1000 test split,
and reports macro-averaged metrics in the same style as the reference repo.
"""

import argparse
import datetime
import os
import time

import cv2
import numpy as np
import torch

from src.dataset import load_DC1000_data
from src.metrics import calculate_metrics
from src.models import DoubleUnet, UNet
from src.utils import create_dir, print_and_save, seeding


MODEL_REGISTRY: dict[str, type] = {
    "UNet": UNet,
    "DoubleUnet": DoubleUnet,
}


def load_state_dict(checkpoint_path: str, device: torch.device) -> dict:
    try:
        return torch.load(checkpoint_path, map_location=device, weights_only=True)
    except TypeError:
        return torch.load(checkpoint_path, map_location=device)


def load_sample(
    image_path: str,
    mask_path: str,
    size: tuple[int, int],
) -> tuple[torch.Tensor, torch.Tensor, np.ndarray, np.ndarray]:
    image = cv2.imread(image_path, cv2.IMREAD_COLOR)
    assert image is not None, f"failed to read image: {image_path}"
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    assert mask is not None, f"failed to read mask: {mask_path}"

    original_image = image.copy()
    original_mask = mask.copy()

    image = cv2.resize(image, size, interpolation=cv2.INTER_NEAREST)
    image = np.transpose(image, (2, 0, 1)).astype(np.float32) / 255.0
    image = torch.from_numpy(np.expand_dims(image, axis=0))

    mask = cv2.resize(mask, size, interpolation=cv2.INTER_NEAREST)
    mask = (mask > 127).astype(np.float32)
    mask = torch.from_numpy(mask[np.newaxis, np.newaxis, ...])

    return image, mask, original_image, original_mask


def prediction_to_rgb(y_pred: torch.Tensor) -> np.ndarray:
    y_pred_np = y_pred[0].detach().cpu().numpy()
    y_pred_np = np.squeeze(y_pred_np, axis=0)
    y_pred_np = (y_pred_np > 0.5).astype(np.uint8) * 255
    y_pred_np = np.expand_dims(y_pred_np, axis=-1)
    return np.repeat(y_pred_np, 3, axis=2)


def save_prediction_artifacts(
    save_dir: str,
    image_path: str,
    original_image: np.ndarray,
    original_mask: np.ndarray,
    prediction_rgb: np.ndarray,
) -> None:
    height, width = original_mask.shape
    prediction_rgb = cv2.resize(
        prediction_rgb, (width, height), interpolation=cv2.INTER_NEAREST
    )
    mask_rgb = np.repeat(original_mask[..., np.newaxis], 3, axis=2)
    separator = np.full((height, 10, 3), 255, dtype=np.uint8)
    joint = np.concatenate(
        [original_image, separator, mask_rgb, separator, prediction_rgb], axis=1
    )

    filename = os.path.basename(image_path)
    cv2.imwrite(os.path.join(save_dir, "pred", filename), prediction_rgb)
    cv2.imwrite(os.path.join(save_dir, "joint", filename), joint)


@torch.no_grad()
def evaluate(
    model,
    images: list[str],
    masks: list[str],
    size: tuple[int, int],
    device: torch.device,
    save_dir: str | None = None,
) -> tuple[float, np.ndarray, float, float]:
    total_loss = 0.0
    total_metrics = np.zeros(7, dtype=np.float64)
    inference_times: list[float] = []

    for image_path, mask_path in zip(images, masks):
        image, mask, original_image, original_mask = load_sample(
            image_path, mask_path, size
        )
        image = image.to(device=device, dtype=torch.float32)
        mask = mask.to(device=device, dtype=torch.float32)

        start_time = time.time()
        out = model({"images": image, "masks": mask})
        y_pred = torch.sigmoid(out["prediction"])
        inference_times.append(time.time() - start_time)

        total_loss += out["loss"].item()
        total_metrics += np.asarray(calculate_metrics(mask, y_pred), dtype=np.float64)

        if save_dir is not None:
            save_prediction_artifacts(
                save_dir,
                image_path,
                original_image,
                original_mask,
                prediction_to_rgb(y_pred),
            )

    n_samples = len(images)
    assert n_samples > 0, "test split is empty — check data_path"

    average_loss = total_loss / n_samples
    average_metrics = total_metrics / n_samples
    mean_time = float(np.mean(inference_times)) if inference_times else 0.0
    mean_fps = (1.0 / mean_time) if mean_time > 0 else 0.0
    return average_loss, average_metrics, mean_time, mean_fps


def main():
    seeding(42)

    parser = argparse.ArgumentParser(description="Evaluate a segmentation model on DC1000 test set")
    parser.add_argument(
        "--model", type=str, default="UNet", choices=list(MODEL_REGISTRY.keys())
    )
    parser.add_argument("--data_path", type=str, default="data/DC1000")
    parser.add_argument("--checkpoint", type=str, default=None)
    parser.add_argument("--image_size", type=int, default=384)
    parser.add_argument(
        "--save-preds",
        action="store_true",
        help="Save predicted masks and side-by-side visualizations",
    )
    parser.add_argument(
        "--save-dir",
        type=str,
        default=None,
        help="Directory for saved predictions (default: files/{model}/result_map)",
    )
    opt = parser.parse_args()

    file_path = f"files/{opt.model}"
    create_dir(file_path)

    checkpoint_path = opt.checkpoint or f"{file_path}/checkpoint.pth"
    if not os.path.exists(checkpoint_path):
        raise FileNotFoundError(f"checkpoint not found: {checkpoint_path}")

    test_log_path = f"{file_path}/test_log.txt"
    if not os.path.exists(test_log_path):
        with open(test_log_path, "w") as file:
            file.write("\n")

    print_and_save(test_log_path, str(datetime.datetime.now()))
    print_and_save(test_log_path, f"Model: {opt.model}")
    print_and_save(test_log_path, f"Checkpoint: {checkpoint_path}")

    (_, _), (_, _), (test_x, test_y) = load_DC1000_data(opt.data_path)
    print_and_save(test_log_path, f"Dataset Size:\nTest: {len(test_x)}")

    save_dir = None
    if opt.save_preds:
        save_dir = opt.save_dir or f"{file_path}/result_map"
        create_dir(save_dir)
        create_dir(os.path.join(save_dir, "pred"))
        create_dir(os.path.join(save_dir, "joint"))
        print_and_save(test_log_path, f"Saving predictions to: {save_dir}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model_cls = MODEL_REGISTRY[opt.model]
    model = model_cls().to(device)
    model.load_state_dict(load_state_dict(checkpoint_path, device))
    model.eval()

    size = (opt.image_size, opt.image_size)
    average_loss, average_metrics, mean_time, mean_fps = evaluate(
        model=model,
        images=test_x,
        masks=test_y,
        size=size,
        device=device,
        save_dir=save_dir,
    )

    result_str = (
        f"Test Loss: {average_loss:.4f} - Jaccard: {average_metrics[0]:.4f} "
        f"- F1: {average_metrics[1]:.4f} - Recall: {average_metrics[2]:.4f} "
        f"- Precision: {average_metrics[3]:.4f} - Acc: {average_metrics[4]:.4f} "
        f"- F2: {average_metrics[5]:.4f} - HD: {average_metrics[6]:.4f}"
    )
    print_and_save(test_log_path, result_str)
    print_and_save(
        test_log_path,
        f"Mean inference time: {mean_time:.4f}s - FPS: {mean_fps:.2f}",
    )


if __name__ == "__main__":
    main()