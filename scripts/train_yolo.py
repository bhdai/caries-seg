"""Train YOLOv11-n on the Tufts Dental Dataset (Stage 1: Tooth Detection)
=======================================================================

Thin wrapper around the Ultralytics Python API. Trains a YOLOv11-n model
on the prepared Tufts YOLO dataset to detect individual teeth in panoramic
dental radiographs.

Prerequisites:
  - Run scripts/prepare_yolo_data.py first to generate data/tufts_yolo/
    with images, labels, and tufts_yolo.yaml.

Output:
  - Best weights saved to files/yolo_tooth/train/weights/best.pt
  - Ultralytics may suffix the run name with an integer index if the output
    directory already exists; the script always prints the actual save path.

Usage::

    # Default: 200 epochs, imgsz=640, auto-batch, yolo11n.pt pretrained weights
    python scripts/train_yolo.py

    # Custom epochs and batch size
    python scripts/train_yolo.py --epochs 100 --batch 16

    # Resume from the last checkpoint of a previously interrupted run
    python scripts/train_yolo.py --resume

    # Enable Weights & Biases logging
    python scripts/train_yolo.py --wandb

    # Custom wandb project and run name
    python scripts/train_yolo.py --wandb --wandb-project my-project --wandb-run-name exp1
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env so WANDB_API_KEY is available before wandb is imported.
# Silent when .env is absent — it is optional.
load_dotenv(dotenv_path=".env", override=False)

import wandb  # noqa: E402


def main() -> None:
    """Train YOLOv11-n on the prepared Tufts dental YOLO dataset.

    CLI args:
      --data     Path to Ultralytics dataset YAML (default: data/tufts_yolo/tufts_yolo.yaml)
      --epochs   Number of training epochs (default: 200)
      --imgsz    Input image size in pixels (default: 640)
      --batch    Batch size; -1 for Ultralytics auto-batch (default: -1)
      --weights  Pretrained weights to fine-tune from (default: yolo11n.pt)
      --project  Ultralytics project directory (default: files/yolo_tooth)
      --name     Run name inside the project directory (default: train)
      --resume   Flag: resume training from last checkpoint in --project/--name/weights/last.pt
      --wandb    Flag: enable Weights & Biases logging
      --wandb-project  WandB project name (default: carries-seg or $WANDB_PROJECT)
      --wandb-run-name Optional friendly name for this wandb run
    """
    parser = argparse.ArgumentParser(
        description="Train YOLOv11-n on the prepared Tufts dental YOLO dataset."
    )
    parser.add_argument(
        "--data",
        type=str,
        default="data/tufts_yolo/tufts_yolo.yaml",
        help="Path to the Ultralytics dataset YAML (default: data/tufts_yolo/tufts_yolo.yaml)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=200,
        help="Number of training epochs (default: 200)",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Input image size in pixels (default: 640)",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=-1,
        help="Batch size; -1 for Ultralytics auto-batch (default: -1)",
    )
    parser.add_argument(
        "--weights",
        type=str,
        default="yolo11n.pt",
        help="Pretrained weights to fine-tune from (default: yolo11n.pt)",
    )
    parser.add_argument(
        "--project",
        type=str,
        default="files/yolo_tooth",
        help="Ultralytics project directory (default: files/yolo_tooth)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="train",
        help="Run name inside the project directory (default: train)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Resume training from the last checkpoint at "
            "--project/--name/weights/last.pt"
        ),
    )
    parser.add_argument(
        "--wandb",
        action="store_true",
        help="Enable Weights & Biases logging",
    )
    parser.add_argument(
        "--wandb-project",
        type=str,
        default=os.getenv("WANDB_PROJECT", "carries-seg"),
        help="WandB project name (default: carries-seg or $WANDB_PROJECT)",
    )
    parser.add_argument(
        "--wandb-run-name",
        type=str,
        default=None,
        help="Optional friendly name for this wandb run",
    )
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Validate that the dataset YAML exists before loading the heavy
    # Ultralytics package. Fail early with a clear error message.
    # ------------------------------------------------------------------
    data_path = Path(args.data)
    if not data_path.exists():
        print(
            f"ERROR: Dataset YAML not found: {data_path}\n"
            "       Run  python scripts/prepare_yolo_data.py  first to generate it.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ------------------------------------------------------------------
    # Determine which weights to load.
    #
    # When resuming, Ultralytics must be given the path to last.pt so it
    # can locate the interrupted run's state. We compute the expected path
    # and report a clear error if it is missing rather than silently
    # starting a new run.
    # ------------------------------------------------------------------
    if args.resume:
        last_ckpt = Path(args.project) / args.name / "weights" / "last.pt"
        if not last_ckpt.exists():
            print(
                f"ERROR: --resume was requested but last checkpoint not found:\n"
                f"       {last_ckpt}\n"
                "       Omit --resume to start a fresh training run.",
                file=sys.stderr,
            )
            sys.exit(1)
        weights = str(last_ckpt)
        print(f"Resuming from checkpoint: {last_ckpt}")
    else:
        weights = args.weights

    # ------------------------------------------------------------------
    # Load model — deferred import to keep startup fast when the user
    # only runs --help or encounters a validation error above.
    # ------------------------------------------------------------------
    from ultralytics import YOLO  # noqa: PLC0415

    model = YOLO(weights)

    # ------------------------------------------------------------------
    # Echo effective configuration before starting the (potentially long)
    # training run so the user can verify settings at a glance.
    # ------------------------------------------------------------------
    batch_label = "auto" if args.batch == -1 else str(args.batch)
    print(f"Dataset   : {data_path.resolve()}")
    print(f"Weights   : {weights}")
    print(f"Epochs    : {args.epochs}")
    print(f"Image size: {args.imgsz}")
    print(f"Batch     : {batch_label}")
    print(f"Output    : {args.project}/{args.name}")
    print(f"WandB     : {'enabled' if args.wandb else 'disabled'}")
    print()

    # ------------------------------------------------------------------
    # Initialise WandB.
    #
    # wandb.init() must be called before model.train() so that Ultralytics
    # picks up the active run via its built-in WandB callback. When wandb
    # is disabled every wandb call is a no-op (mode="disabled").
    # ------------------------------------------------------------------
    wandb.init(
        mode="online" if args.wandb else "disabled",
        project=args.wandb_project,
        name=args.wandb_run_name,
        config={
            "model": args.weights,
            "data": str(data_path.resolve()),
            "epochs": args.epochs,
            "imgsz": args.imgsz,
            "batch": args.batch,
        },
    )

    # ------------------------------------------------------------------
    # Train
    #
    # exist_ok=True on resume prevents Ultralytics from auto-incrementing
    # the run name (e.g. "train2") when the output directory already exists.
    # For fresh runs exist_ok=False (default) so each new run gets its own
    # directory if "train" is already taken.
    # ------------------------------------------------------------------
    results = model.train(
        data=str(data_path.resolve()),  # absolute path avoids cwd ambiguity
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=args.project,
        name=args.name,
        resume=args.resume,
        exist_ok=args.resume,
    )

    # ------------------------------------------------------------------
    # Report output paths — results.save_dir is the actual run directory
    # (may carry an auto-incremented integer suffix on fresh runs).
    # ------------------------------------------------------------------
    save_dir = Path(results.save_dir)
    best_weights = save_dir / "weights" / "best.pt"

    print()
    print("Training complete.")
    print(f"  Save directory : {save_dir}")
    print(f"  Best weights   : {best_weights}")

    if not best_weights.exists():
        print(
            f"  WARNING: best.pt not found at the expected path.\n"
            f"           Check {save_dir / 'weights'}/ for available checkpoints.",
            file=sys.stderr,
        )

    wandb.finish()


if __name__ == "__main__":
    main()
