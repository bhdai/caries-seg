"""
Training Script — Stage 2 Caries Segmentation on Cropped Teeth
===============================================================

Trains a segmentation model (UNet, DoubleUnet, or AttentionUNet) on the
DC1000_cropped dataset produced by ``scripts/extract_tooth_crops.py``.

Key differences from ``train.py`` (Stage 1 baseline):
  - Uses ``CroppedToothDataset`` / ``load_cropped_data()`` instead of DC1000.
  - Default image size is 256×256 (crops are small; 384 would over-scale).
  - Default batch size is 8 (crops fit more per GPU pass than panoramics).
  - Optional ``--balanced`` flag to train on the 1:1 caries/non-caries subset.
  - ``MODEL_REGISTRY`` includes AttentionUNet alongside UNet and DoubleUnet.
  - Checkpoints are saved under ``files/stage2_{model}/``.
  - Augmentation ranges are slightly tighter than Stage 1 (crops already centred).

Training loop, loss, optimizer, scheduler, early stopping, and wandb
integration are structurally identical to ``train.py``.
"""

import argparse
import datetime
import os
import time

import albumentations as A
import cv2
import numpy as np
import torch
from dotenv import load_dotenv
from torch.utils.data import DataLoader

# Load .env if present so WANDB_API_KEY is available before wandb is imported.
# We intentionally do not fail when .env is absent — it is optional.
load_dotenv(dotenv_path=".env", override=False)

import wandb  # noqa: E402  (must come after load_dotenv)
from src.dataset import CroppedToothDataset, load_cropped_data
from src.metrics import calculate_metrics
from src.models import AttentionUNet, DoubleUnet, UNet
from src.utils import create_dir, epoch_time, print_and_save, seeding, shuffling

# ==============================================================================
# Model Registry
# ==============================================================================
#
# Maps CLI --model string to a constructor. All three models share the same
# forward signature: input dict {"images": ..., "masks": ...} → output dict
# {"prediction": logits, "loss": scalar}.

MODEL_REGISTRY: dict[str, type] = {
    "UNet": UNet,
    "DoubleUnet": DoubleUnet,
    "AttentionUNet": AttentionUNet,
}


# ==============================================================================
# Training & Evaluation Loops
# ==============================================================================
#
# Identical to train.py — the segmentation loop is model-agnostic.


def train_one_epoch(
    model: torch.nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
) -> tuple[float, list[float]]:
    """Run one training epoch and return mean loss + metrics.

    Returns:
        (epoch_loss, [jaccard, f1, recall, precision])
    """
    model.train()

    epoch_loss = 0.0
    epoch_jac = 0.0
    epoch_f1 = 0.0
    epoch_recall = 0.0
    epoch_precision = 0.0

    for x, y in loader:
        x = x.to(device, dtype=torch.float32)
        y = y.to(device, dtype=torch.float32)

        optimizer.zero_grad()
        out = model({"images": x, "masks": y})
        loss = out["loss"]
        loss.backward()
        optimizer.step()
        epoch_loss += loss.item()

        y_pred = torch.sigmoid(out["prediction"])
        batch_jac, batch_f1, batch_recall, batch_precision = [], [], [], []
        for yt, yp in zip(y, y_pred):
            score = calculate_metrics(yt, yp)
            batch_jac.append(score[0])
            batch_f1.append(score[1])
            batch_recall.append(score[2])
            batch_precision.append(score[3])

        epoch_jac += np.mean(batch_jac)
        epoch_f1 += np.mean(batch_f1)
        epoch_recall += np.mean(batch_recall)
        epoch_precision += np.mean(batch_precision)

    n = len(loader)
    return epoch_loss / n, [
        epoch_jac / n,
        epoch_f1 / n,
        epoch_recall / n,
        epoch_precision / n,
    ]


@torch.no_grad()
def evaluate(
    model: torch.nn.Module,
    loader: DataLoader,
    device: torch.device,
) -> tuple[float, list[float]]:
    """Evaluate model on a validation/test loader.

    Returns:
        (epoch_loss, [jaccard, f1, recall, precision])
    """
    model.eval()

    epoch_loss = 0.0
    epoch_jac = 0.0
    epoch_f1 = 0.0
    epoch_recall = 0.0
    epoch_precision = 0.0

    for x, y in loader:
        x = x.to(device, dtype=torch.float32)
        y = y.to(device, dtype=torch.float32)

        out = model({"images": x, "masks": y})
        loss = out["loss"]
        epoch_loss += loss.item()

        y_pred = torch.sigmoid(out["prediction"])
        batch_jac, batch_f1, batch_recall, batch_precision = [], [], [], []
        for yt, yp in zip(y, y_pred):
            score = calculate_metrics(yt, yp)
            batch_jac.append(score[0])
            batch_f1.append(score[1])
            batch_recall.append(score[2])
            batch_precision.append(score[3])

        epoch_jac += np.mean(batch_jac)
        epoch_f1 += np.mean(batch_f1)
        epoch_recall += np.mean(batch_recall)
        epoch_precision += np.mean(batch_precision)

    n = len(loader)
    return epoch_loss / n, [
        epoch_jac / n,
        epoch_f1 / n,
        epoch_recall / n,
        epoch_precision / n,
    ]


# ==============================================================================
# Main
# ==============================================================================


def main() -> None:
    seeding(42)

    parser = argparse.ArgumentParser(
        description="Train a segmentation model on the DC1000_cropped tooth crop dataset (Stage 2)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="AttentionUNet",
        choices=list(MODEL_REGISTRY.keys()),
        help="Model architecture (default: AttentionUNet)",
    )
    parser.add_argument(
        "--data_path",
        type=str,
        default="data/DC1000_cropped",
        help="Root of the cropped tooth dataset (default: data/DC1000_cropped)",
    )
    parser.add_argument(
        "--balanced",
        action="store_true",
        help="Train on the balanced 1:1 caries/non-caries subset",
    )
    parser.add_argument(
        "--image_size",
        type=int,
        default=256,
        help="Square resize dimension for crops (default: 256)",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=8,
        help="Mini-batch size (default: 8)",
    )
    parser.add_argument(
        "--lr",
        type=float,
        default=1e-4,
        help="Initial learning rate (default: 1e-4)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=500,
        help="Maximum number of training epochs (default: 500)",
    )
    parser.add_argument(
        "--patience",
        type=int,
        default=50,
        help="Early stopping patience in epochs (default: 50)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume training from checkpoint if it exists",
    )
    parser.add_argument(
        "--wandb",
        action="store_true",
        help="Enable Weights & Biases logging",
    )
    parser.add_argument(
        "--wandb-project",
        type=str,
        default=os.getenv("WANDB_PROJECT", "caries-seg-stage2"),
        help="wandb project name (default: caries-seg-stage2 or $WANDB_PROJECT)",
    )
    parser.add_argument(
        "--wandb-run-name",
        type=str,
        default=None,
        help="Optional friendly name for this wandb run",
    )
    opt = parser.parse_args()

    # Re-seed after argparse in case --seed differs from default.
    seeding(opt.seed)

    # ----- directories -----
    file_path = f"files/stage2_{opt.model}"
    create_dir(file_path)

    train_log_path = f"{file_path}/train_log.txt"
    if not os.path.exists(train_log_path):
        with open(train_log_path, "w") as f:
            f.write("\n")

    print_and_save(train_log_path, str(datetime.datetime.now()))

    # ----- hyperparameters -----
    size = (opt.image_size, opt.image_size)
    checkpoint_path = f"{file_path}/checkpoint.pth"

    data_str = (
        f"Model: {opt.model}\n"
        f"Image Size: {size}\nBatch Size: {opt.batch_size}\nLR: {opt.lr}\n"
        f"Epochs: {opt.epochs}\nEarly Stopping Patience: {opt.patience}\n"
        f"Balanced: {opt.balanced}\nData: {opt.data_path}\n"
    )
    print_and_save(train_log_path, data_str)

    # ----- wandb initialisation -----
    #
    # Entirely optional — pass --wandb to activate. When disabled every
    # wandb call below is a no-op (disabled mode), so no if-guards needed.
    wandb.init(
        mode="online" if opt.wandb else "disabled",
        project=opt.wandb_project,
        name=opt.wandb_run_name,
        config={
            "model": opt.model,
            "image_size": opt.image_size,
            "batch_size": opt.batch_size,
            "lr": opt.lr,
            "num_epochs": opt.epochs,
            "early_stopping_patience": opt.patience,
            "balanced": opt.balanced,
            "data_path": opt.data_path,
            "seed": opt.seed,
        },
    )

    # ----- dataset -----
    (train_x, train_y), (valid_x, valid_y), (test_x, test_y) = load_cropped_data(
        opt.data_path, balanced=opt.balanced
    )
    train_x, train_y = shuffling(train_x, train_y)

    data_str = (
        f"Dataset Size:\nTrain: {len(train_x)} - Valid: {len(valid_x)} - Test: {len(test_x)}\n"
    )
    print_and_save(train_log_path, data_str)

    # ----- augmentation (train split only) -----
    #
    # Crops are already centred on individual teeth, so we tighten the shift
    # to 0.0 (no translation) and keep rotation/scale small to avoid
    # cutting off the tooth edges.
    transform = A.Compose(
        [
            A.HorizontalFlip(p=0.5),
            A.ShiftScaleRotate(
                shift_limit=0.0,
                scale_limit=0.05,
                rotate_limit=15,
                interpolation=cv2.INTER_LINEAR,
                border_mode=cv2.BORDER_CONSTANT,
                p=0.3,
            ),
            A.RandomBrightnessContrast(p=0.3),
        ]
    )

    train_dataset = CroppedToothDataset(
        train_x, train_y, size=opt.image_size, transform=transform
    )
    valid_dataset = CroppedToothDataset(
        valid_x, valid_y, size=opt.image_size, transform=None
    )

    train_loader = DataLoader(
        dataset=train_dataset,
        batch_size=opt.batch_size,
        shuffle=True,
        num_workers=2,
    )
    valid_loader = DataLoader(
        dataset=valid_dataset,
        batch_size=opt.batch_size,
        shuffle=False,
        num_workers=2,
    )

    assert len(train_loader) > 0, "train loader is empty — check data_path"
    assert len(valid_loader) > 0, "valid loader is empty — check data_path"

    # ----- model -----
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model_cls = MODEL_REGISTRY[opt.model]
    model = model_cls().to(device)

    print(f"Model: {opt.model} | Device: {device}")

    # Resume from checkpoint if requested and a checkpoint exists.
    if opt.resume and os.path.exists(checkpoint_path):
        model.load_state_dict(
            torch.load(checkpoint_path, map_location=device, weights_only=True)
        )
        print_and_save(train_log_path, f"Resumed from checkpoint: {checkpoint_path}")

    optimizer = torch.optim.Adam(model.parameters(), lr=opt.lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, "min", patience=5
    )

    print_and_save(train_log_path, "Optimizer: Adam\n")

    # ----- training loop -----
    best_valid_f1 = 0.0
    early_stopping_count = 0

    for epoch in range(opt.epochs):
        start_time = time.time()

        train_loss, train_metrics = train_one_epoch(
            model, train_loader, optimizer, device
        )
        valid_loss, valid_metrics = evaluate(model, valid_loader, device)
        scheduler.step(valid_loss)

        # Checkpoint on best validation F1.
        if valid_metrics[1] > best_valid_f1:
            data_str = (
                f"Valid F1 improved from {best_valid_f1:2.4f} to "
                f"{valid_metrics[1]:2.4f}. Saving checkpoint: {checkpoint_path}"
            )
            print_and_save(train_log_path, data_str)

            best_valid_f1 = valid_metrics[1]
            torch.save(model.state_dict(), checkpoint_path)
            early_stopping_count = 0
        else:
            early_stopping_count += 1

        end_time = time.time()
        epoch_mins, epoch_secs = epoch_time(start_time, end_time)

        data_str = (
            f"Epoch: {epoch + 1:02} | Epoch Time: {epoch_mins}m {epoch_secs}s\n"
        )
        data_str += (
            f"\tTrain Loss: {train_loss:.4f} - Jaccard: {train_metrics[0]:.4f} "
            f"- F1: {train_metrics[1]:.4f} - Recall: {train_metrics[2]:.4f} "
            f"- Precision: {train_metrics[3]:.4f}\n"
        )
        data_str += (
            f"\t Val. Loss: {valid_loss:.4f} - Jaccard: {valid_metrics[0]:.4f} "
            f"- F1: {valid_metrics[1]:.4f} - Recall: {valid_metrics[2]:.4f} "
            f"- Precision: {valid_metrics[3]:.4f}\n"
        )
        print_and_save(train_log_path, data_str)

        wandb.log(
            {
                "epoch": epoch + 1,
                "train/loss": train_loss,
                "train/jaccard": train_metrics[0],
                "train/f1": train_metrics[1],
                "train/recall": train_metrics[2],
                "train/precision": train_metrics[3],
                "val/loss": valid_loss,
                "val/jaccard": valid_metrics[0],
                "val/f1": valid_metrics[1],
                "val/recall": valid_metrics[2],
                "val/precision": valid_metrics[3],
                "val/best_f1": best_valid_f1,
                "lr": optimizer.param_groups[0]["lr"],
            }
        )

        if early_stopping_count == opt.patience:
            data_str = (
                f"Early stopping: validation F1 stopped improving "
                f"for {opt.patience} consecutive epochs.\n"
            )
            print_and_save(train_log_path, data_str)
            break

    wandb.finish()


if __name__ == "__main__":
    main()
