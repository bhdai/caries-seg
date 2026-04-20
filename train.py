"""
Training Script — DC1000 Dental Caries Segmentation
=====================================================

- 384×384 input, batch_size=4, Adam lr=1e-4
- ReduceLROnPlateau on validation loss
- Early stopping (patience 50) on validation F1
- Albumentations augmentation on train only
- Metrics: Jaccard, F1, Recall, Precision per epoch
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
from src.dataset import DC1000Dataset, load_DC1000_data
from src.metrics import calculate_metrics
from src.models import DoubleUnet, UNet
from src.utils import create_dir, epoch_time, print_and_save, seeding, shuffling

# ==============================================================================
# Model Registry
# ==============================================================================
#
# Maps CLI --model string to a constructor. Add new models here.

MODEL_REGISTRY: dict[str, type] = {
    "UNet": UNet,
    "DoubleUnet": DoubleUnet,
}


# ==============================================================================
# Training & Evaluation Loops
# ==============================================================================


def train_one_epoch(model, loader, optimizer, device):
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

        # Per-batch metrics
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
def evaluate(model, loader, device):
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


def main():
    seeding(42)

    parser = argparse.ArgumentParser(description="Train a segmentation model on DC1000")
    parser.add_argument(
        "--model", type=str, default="UNet", choices=list(MODEL_REGISTRY.keys())
    )
    parser.add_argument("--data_path", type=str, default="data/DC1000")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume training from checkpoint if it exists",
    )
    parser.add_argument(
        "--wandb", action="store_true", help="Enable Weights & Biases logging"
    )
    parser.add_argument(
        "--wandb-project",
        type=str,
        default=os.getenv("WANDB_PROJECT", "carries-seg"),
        help="wandb project name (default: carries-seg or $WANDB_PROJECT)",
    )
    parser.add_argument(
        "--wandb-run-name",
        type=str,
        default=None,
        help="Optional friendly name for this wandb run",
    )
    opt = parser.parse_args()

    # ----- directories -----
    file_path = f"files/{opt.model}"
    create_dir(file_path)

    train_log_path = f"{file_path}/train_log.txt"
    if not os.path.exists(train_log_path):
        with open(train_log_path, "w") as f:
            f.write("\n")

    print_and_save(train_log_path, str(datetime.datetime.now()))

    # ----- hyperparameters -----
    image_size = 384
    size = (image_size, image_size)
    batch_size = 4
    num_epochs = 500
    lr = 1e-4
    early_stopping_patience = 50
    checkpoint_path = f"{file_path}/checkpoint.pth"

    data_str = (
        f"Image Size: {size}\nBatch Size: {batch_size}\nLR: {lr}\n"
        f"Epochs: {num_epochs}\nEarly Stopping Patience: {early_stopping_patience}\n"
    )
    print_and_save(train_log_path, data_str)

    # ----- wandb initialisation -----
    #
    # We keep wandb entirely optional: pass --wandb to activate. When disabled
    # every wandb call below is a no-op via the disabled mode, so the rest of
    # the training loop never needs an `if opt.wandb` guard.
    wandb.init(
        mode="online" if opt.wandb else "disabled",
        project=opt.wandb_project,
        name=opt.wandb_run_name,
        config={
            "model": opt.model,
            "image_size": image_size,
            "batch_size": batch_size,
            "lr": lr,
            "num_epochs": num_epochs,
            "early_stopping_patience": early_stopping_patience,
            "data_path": opt.data_path,
        },
    )

    # ----- dataset -----
    (train_x, train_y), (valid_x, valid_y), (test_x, test_y) = load_DC1000_data(
        opt.data_path
    )
    train_x, train_y = shuffling(train_x, train_y)

    data_str = f"Dataset Size:\nTrain: {len(train_x)} - Valid: {len(valid_x)} - Test: {len(test_x)}\n"
    print_and_save(train_log_path, data_str)

    # ----- augmentation (train only) -----
    transform = A.Compose(
        [
            A.HorizontalFlip(p=0.5),
            A.ShiftScaleRotate(
                shift_limit=0.05,
                scale_limit=0.05,
                rotate_limit=15,
                interpolation=cv2.INTER_LINEAR,
                border_mode=cv2.BORDER_CONSTANT,
                p=0.3,
            ),
            A.RandomBrightnessContrast(p=0.3),
        ]
    )

    train_dataset = DC1000Dataset(train_x, train_y, size, transform=transform)
    valid_dataset = DC1000Dataset(valid_x, valid_y, size, transform=None)

    train_loader = DataLoader(
        dataset=train_dataset, batch_size=batch_size, shuffle=True, num_workers=2
    )
    valid_loader = DataLoader(
        dataset=valid_dataset, batch_size=batch_size, shuffle=False, num_workers=2
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

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer,
        "min",
        patience=5,
    )

    print_and_save(train_log_path, "Optimizer: Adam\n")

    # ----- training loop -----
    best_valid_f1 = 0.0
    early_stopping_count = 0

    for epoch in range(num_epochs):
        start_time = time.time()

        train_loss, train_metrics = train_one_epoch(
            model, train_loader, optimizer, device
        )
        valid_loss, valid_metrics = evaluate(model, valid_loader, device)
        scheduler.step(valid_loss)

        # Checkpoint on best validation F1
        if valid_metrics[1] > best_valid_f1:
            data_str = (
                f"Valid F1 improved from {best_valid_f1:2.4f} to {valid_metrics[1]:2.4f}. "
                f"Saving checkpoint: {checkpoint_path}"
            )
            print_and_save(train_log_path, data_str)

            best_valid_f1 = valid_metrics[1]
            torch.save(model.state_dict(), checkpoint_path)
            early_stopping_count = 0
        else:
            early_stopping_count += 1

        end_time = time.time()
        epoch_mins, epoch_secs = epoch_time(start_time, end_time)

        data_str = f"Epoch: {epoch + 1:02} | Epoch Time: {epoch_mins}m {epoch_secs}s\n"
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

        # Log scalar metrics to wandb. When wandb is disabled this is a no-op.
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

        if early_stopping_count == early_stopping_patience:
            data_str = (
                f"Early stopping: validation F1 stopped improving "
                f"for {early_stopping_patience} consecutive epochs.\n"
            )
            print_and_save(train_log_path, data_str)
            break

    wandb.finish()


if __name__ == "__main__":
    main()
