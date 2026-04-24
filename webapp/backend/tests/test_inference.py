"""Unit tests for Phase 3 — Inference Pipeline.

Covered:
  preprocessing.load_image          — valid file, missing file, corrupt file
  preprocessing.prepare_tensor      — output shape
  preprocessing.tensor_to_mask      — thresholding, resize
  inference.registry.ModelRegistry  — missing arch raises KeyError
  inference.two_stage.run_two_stage — zero detections, union composition

All tests are pure-Python; no database or Docker container is required.
YOLO and segmentation models are replaced with lightweight stubs so the
tests run quickly without GPU or real checkpoints.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch
import torch.nn as nn

# ---------------------------------------------------------------------------
# Make sure the monorepo root (containing src/) is importable.
# ---------------------------------------------------------------------------
BACKEND_ROOT = Path(__file__).resolve().parents[1]
MONOREPO_ROOT = BACKEND_ROOT.parents[1]
if str(MONOREPO_ROOT) not in sys.path:
    sys.path.insert(0, str(MONOREPO_ROOT))

from app.inference.preprocessing import (
    load_image,
    prepare_tensor,
    tensor_to_mask,
)
from app.inference.registry import ModelRegistry
from app.inference.single_stage import BBox, InferenceOutput


# ==============================================================================
# Helpers
# ==============================================================================


def _write_valid_png(path: Path) -> None:
    """Write a minimal 64×32 BGR PNG to *path*."""
    import cv2

    img = np.zeros((32, 64, 3), dtype=np.uint8)
    img[4:28, 4:60] = 255
    ok, buf = cv2.imencode(".png", img)
    assert ok
    path.write_bytes(buf.tobytes())


class _PassThroughModel(nn.Module):
    """Segmentation model stub that returns all-positive logits.

    A positive logit (> 0) passes through sigmoid > 0.5, so
    ``tensor_to_mask`` will mark every pixel as caries.
    """

    def forward(self, sample: dict) -> dict:
        images = sample["images"]
        # Return a single-channel logit map filled with 10.0 (≈ sigmoid → 1.0).
        return {"prediction": torch.full_like(images[:, :1, :, :], 10.0)}


class _ZeroModel(nn.Module):
    """Segmentation model stub that returns all-negative logits (no caries)."""

    def forward(self, sample: dict) -> dict:
        images = sample["images"]
        return {"prediction": torch.full_like(images[:, :1, :, :], -10.0)}


# ==============================================================================
# preprocessing.load_image
# ==============================================================================


def test_load_image_valid(tmp_path: Path) -> None:
    """Valid PNG → float32 BGR array with values in [0, 1]."""
    img_path = tmp_path / "test.png"
    _write_valid_png(img_path)

    img = load_image(img_path)

    assert img.dtype == np.float32
    assert img.ndim == 3
    assert img.shape[2] == 3
    assert img.shape == (32, 64, 3)
    assert float(img.min()) >= 0.0
    assert float(img.max()) <= 1.0


def test_load_image_missing(tmp_path: Path) -> None:
    """Non-existent path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_image(tmp_path / "does_not_exist.png")


def test_load_image_corrupt(tmp_path: Path) -> None:
    """File that exists but is not a valid image raises ValueError."""
    bad_path = tmp_path / "bad.png"
    bad_path.write_bytes(b"\x89PNG\r\n" + b"\x00" * 50)

    with pytest.raises(ValueError, match="cv2.imread returned None"):
        load_image(bad_path)


# ==============================================================================
# preprocessing.prepare_tensor
# ==============================================================================


def test_prepare_tensor_shape() -> None:
    """Output tensor has shape (1, 3, target_h, target_w) on the requested device."""
    img = np.random.rand(100, 200, 3).astype(np.float32)
    tensor = prepare_tensor(img, target_h=64, target_w=128, device="cpu")

    assert tensor.shape == (1, 3, 64, 128)
    assert tensor.dtype == torch.float32
    assert tensor.device.type == "cpu"


def test_prepare_tensor_values_in_range() -> None:
    """Tensor values stay in [0, 1] — no extra normalisation is applied."""
    img = np.ones((50, 50, 3), dtype=np.float32) * 0.5
    tensor = prepare_tensor(img, target_h=32, target_w=32, device="cpu")

    assert float(tensor.min()) >= 0.0
    assert float(tensor.max()) <= 1.0


# ==============================================================================
# core.config.Settings device resolution
# ==============================================================================


def test_settings_auto_resolves_to_cpu_when_cuda_is_unavailable(tmp_path: Path) -> None:
    """Auto device selection falls back to CPU when CUDA is unavailable."""
    from app.core.config import Settings

    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        STORAGE_ROOT=tmp_path / "storage",
        MODEL_ROOT=tmp_path / "models",
    )

    with patch("torch.cuda.is_available", return_value=False):
        assert settings.resolved_device == "cpu"


def test_settings_auto_resolves_to_cuda_when_available(tmp_path: Path) -> None:
    """Auto device selection prefers CUDA when Torch reports a GPU."""
    from app.core.config import Settings

    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        STORAGE_ROOT=tmp_path / "storage",
        MODEL_ROOT=tmp_path / "models",
    )

    with patch("torch.cuda.is_available", return_value=True):
        assert settings.resolved_device == "cuda"


def test_settings_explicit_cuda_requires_available_gpu(tmp_path: Path) -> None:
    """Explicit CUDA selection fails fast instead of silently using CPU."""
    from app.core.config import Settings

    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        STORAGE_ROOT=tmp_path / "storage",
        MODEL_ROOT=tmp_path / "models",
        DEVICE="cuda",
    )

    with patch("torch.cuda.is_available", return_value=False):
        with pytest.raises(AssertionError, match="DEVICE='cuda'"):
            _ = settings.resolved_device


# ==============================================================================
# preprocessing.tensor_to_mask
# ==============================================================================


def test_tensor_to_mask_all_positive() -> None:
    """All-positive logits → all-255 output mask."""
    logits = torch.full((1, 1, 16, 16), 10.0)
    mask = tensor_to_mask(logits, original_h=32, original_w=64)

    assert mask.dtype == np.uint8
    assert mask.shape == (32, 64)
    assert (mask == 255).all()


def test_tensor_to_mask_all_negative() -> None:
    """All-negative logits → all-0 output mask."""
    logits = torch.full((1, 1, 16, 16), -10.0)
    mask = tensor_to_mask(logits, original_h=32, original_w=64)

    assert (mask == 0).all()


def test_tensor_to_mask_threshold_at_zero() -> None:
    """Zero logit → sigmoid(0) = 0.5 → threshold 0.5 ≥ 0.5 → 255."""
    logits = torch.zeros((1, 1, 1, 1))
    mask = tensor_to_mask(logits, original_h=4, original_w=4)

    assert (mask == 255).all()


def test_tensor_to_mask_resize() -> None:
    """Output shape matches the requested (original_h, original_w)."""
    logits = torch.rand(1, 1, 8, 8)
    mask = tensor_to_mask(logits, original_h=100, original_w=200)

    assert mask.shape == (100, 200)


# ==============================================================================
# registry.ModelRegistry
# ==============================================================================


def test_registry_missing_arch_raises_key_error(tmp_path: Path) -> None:
    """get() raises KeyError with a helpful message for an unloaded combination."""
    from app.core.config import Settings

    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        STORAGE_ROOT=tmp_path / "storage",
        MODEL_ROOT=tmp_path / "models",
    )
    reg = ModelRegistry(settings)
    # load_all() with no checkpoints on disk — all models will be absent.
    reg.load_all()

    with pytest.raises(KeyError, match="single_stage.*unet"):
        reg.get("single_stage", "unet")


def test_registry_get_yolo_raises_runtime_error(tmp_path: Path) -> None:
    """get_yolo() raises RuntimeError when YOLO was not loaded at startup."""
    from app.core.config import Settings

    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        STORAGE_ROOT=tmp_path / "storage",
        MODEL_ROOT=tmp_path / "models",
    )
    reg = ModelRegistry(settings)
    reg.load_all()

    with pytest.raises(RuntimeError, match="YOLO weights were not loaded"):
        reg.get_yolo()


def test_registry_loads_model_from_checkpoint(tmp_path: Path) -> None:
    """A valid checkpoint file causes the model to appear in the registry."""
    from app.core.config import Settings
    from src.models import UNet

    # Create a minimal checkpoint: a UNet state dict saved to disk.
    model_dir = tmp_path / "models" / "single-stage" / "UNet"
    model_dir.mkdir(parents=True)
    ckpt_path = model_dir / "checkpoint.pth"
    unet = UNet()
    torch.save(unet.state_dict(), ckpt_path)

    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        STORAGE_ROOT=tmp_path / "storage",
        MODEL_ROOT=tmp_path / "models",
    )
    reg = ModelRegistry(settings)
    reg.load_all()

    model = reg.get("single_stage", "unet")
    assert model is not None
    # Must be in eval mode.
    assert not model.training


# ==============================================================================
# two_stage.run_two_stage — zero detections
# ==============================================================================


def _make_image_result_stub(upload_path: Path) -> MagicMock:
    """Return a minimal ImageResult-like stub."""
    import uuid

    ir = MagicMock()
    ir.upload_path = str(upload_path)
    ir.id = uuid.uuid4()
    return ir


def test_two_stage_zero_detections(tmp_path: Path) -> None:
    """When YOLO returns no boxes, run_two_stage returns a zero mask and empty list."""
    from app.core.config import Settings
    from app.inference.two_stage import run_two_stage

    # Write a real PNG to disk so load_image succeeds.
    img_path = tmp_path / "uploads" / "job1" / "xray.png"
    img_path.parent.mkdir(parents=True)
    _write_valid_png(img_path)

    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        STORAGE_ROOT=tmp_path / "storage",
        MODEL_ROOT=tmp_path / "models",
        DEVICE="cpu",
    )
    (tmp_path / "storage").mkdir(parents=True, exist_ok=True)

    ir = _make_image_result_stub(img_path)

    # YOLO stub that returns no detections.
    yolo_stub = MagicMock()
    empty_result = MagicMock()
    empty_result.boxes = None
    yolo_stub.predict.return_value = [empty_result]

    output = run_two_stage(ir, yolo_stub, _ZeroModel(), settings)

    assert output.bounding_boxes == []
    assert output.mask_path.exists()
    yolo_stub.predict.assert_called_once()
    assert yolo_stub.predict.call_args.kwargs["device"] == "cpu"

    import cv2
    saved_mask = cv2.imread(str(output.mask_path), cv2.IMREAD_GRAYSCALE)
    assert saved_mask is not None
    assert (saved_mask == 0).all()


def test_two_stage_composition_union(tmp_path: Path) -> None:
    """Two overlapping detections produce a union mask (np.maximum semantics)."""
    from app.core.config import Settings
    from app.inference.two_stage import run_two_stage

    img_path = tmp_path / "uploads" / "job2" / "xray.png"
    img_path.parent.mkdir(parents=True)

    # Create a 128×64 image.
    import cv2
    img = np.zeros((64, 128, 3), dtype=np.uint8)
    img[10:50, 10:118] = 200
    ok, buf = cv2.imencode(".png", img)
    assert ok
    img_path.write_bytes(buf.tobytes())

    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        STORAGE_ROOT=tmp_path / "storage",
        MODEL_ROOT=tmp_path / "models",
        DEVICE="cpu",
    )
    (tmp_path / "storage").mkdir(parents=True, exist_ok=True)

    ir = _make_image_result_stub(img_path)

    # Two overlapping boxes covering most of the image.
    # The _PassThroughModel marks every pixel as caries, so the composed
    # mask should be all-255 under the union of the two padded crops.
    box1 = MagicMock()
    box1.xyxy = torch.tensor([[10.0, 5.0, 60.0, 55.0]])
    box1.conf = torch.tensor([0.9])
    box2 = MagicMock()
    box2.xyxy = torch.tensor([[50.0, 5.0, 118.0, 55.0]])
    box2.conf = torch.tensor([0.85])

    # First call returns box1, second returns box2 — but we return both at once.
    combined = MagicMock()
    combined.boxes = MagicMock()
    # xyxy: (2, 4) tensor; conf: (2,) tensor
    combined.boxes.xyxy = torch.tensor([
        [10.0, 5.0, 60.0, 55.0],
        [50.0, 5.0, 118.0, 55.0],
    ])
    combined.boxes.conf = torch.tensor([0.9, 0.85])

    yolo_stub = MagicMock()
    yolo_stub.predict.return_value = [combined]

    output = run_two_stage(ir, yolo_stub, _PassThroughModel(), settings)

    assert len(output.bounding_boxes) == 2
    assert output.mask_path.exists()

    saved_mask = cv2.imread(str(output.mask_path), cv2.IMREAD_GRAYSCALE)
    assert saved_mask is not None
    # Under both detections' padded regions the mask must be 255.
    # Check a pixel clearly inside both crops.
    assert saved_mask[30, 55] == 255
