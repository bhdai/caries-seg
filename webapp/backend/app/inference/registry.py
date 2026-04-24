"""ModelRegistry: eager-load all segmentation checkpoints at startup.

The registry is a module-level singleton initialised by ``init_registry()``
during the FastAPI lifespan.  All inference workers import ``registry``
from this module to retrieve pre-loaded models without re-reading weights
on every request.

Supported combinations (plan § "What We Are NOT Doing" — no AttentionUNet):

    single_stage / unet          → files/single-stage/UNet/checkpoint.pth
    single_stage / double_unet   → files/single-stage/Double-UNet/checkpoint.pth
    two_stage    / unet          → files/two-stage/UNet/checkpoint.pth
    two_stage    / double_unet   → files/two-stage/Double-UNet/checkpoint.pth
    two_stage    / yolo          → two-stage/yolo/.../best.pt  (Ultralytics YOLO)

Missing checkpoints log a WARNING rather than crashing startup so the app
starts with a partial model set (e.g. only single-stage on a CPU-only host
without all weights present).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import torch
import torch.nn as nn

# Import model constructors from the shared src package.
# The src/ directory is copied into the backend container alongside app/.
from src.models import DoubleUnet, UNet

from app.core.config import Settings

if TYPE_CHECKING:
    from ultralytics import YOLO

logger = logging.getLogger(__name__)


# ==============================================================================
# Checkpoint path mapping
# ==============================================================================
#
# Maps (pipeline_type, model_arch) to a tuple of (relative_dir, model_class).
# The checkpoint file is always named "checkpoint.pth" inside that directory.
# AttentionUNet is intentionally absent — no webapp checkpoint exists.

_CHECKPOINT_MAP: dict[tuple[str, str], tuple[str, type[nn.Module]]] = {
    ("single_stage", "unet"): ("single-stage/UNet", UNet),
    ("single_stage", "double_unet"): ("single-stage/Double-UNet", DoubleUnet),
    ("two_stage", "unet"): ("two-stage/UNet", UNet),
    ("two_stage", "double_unet"): ("two-stage/Double-UNet", DoubleUnet),
}

# Relative path from MODEL_ROOT to the YOLO best-weights file.
_YOLO_SUBPATH = "two-stage/yolo/detect/files/yolo_tooth/train/weights/best.pt"


# ==============================================================================
# ModelRegistry
# ==============================================================================


class ModelRegistry:
    """Holds all loaded segmentation models and the YOLO detector.

    Designed as a singleton — create one instance per process (in the
    lifespan) and share it via the module-level ``registry`` variable.

    Args:
        settings: App settings providing ``MODEL_ROOT`` and ``DEVICE``.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._models: dict[str, nn.Module] = {}
        self._yolo: YOLO | None = None

    # ------------------------------------------------------------------
    # Startup loading
    # ------------------------------------------------------------------

    def load_all(self) -> None:
        """Eagerly load all model checkpoints found on disk into memory.

        Logs a WARNING (rather than raising) when a checkpoint file is
        missing so the app starts with a partial model set.  Each model
        is placed in ``eval()`` mode and moved to the configured device.
        """
        resolved_device = self._settings.resolved_device
        logger.info(
            "Initialising inference registry on device=%s (requested=%s, cuda_available=%s)",
            resolved_device,
            self._settings.DEVICE,
            torch.cuda.is_available(),
        )

        for (pipeline_type, model_arch), (dir_name, model_class) in _CHECKPOINT_MAP.items():
            ckpt_path = self._settings.MODEL_ROOT / dir_name / "checkpoint.pth"
            key = f"{pipeline_type}/{model_arch}"

            if not ckpt_path.exists():
                logger.warning(
                    "Checkpoint not found for %s — model will not be available. "
                    "Expected: %s",
                    key,
                    ckpt_path,
                )
                continue

            try:
                # DoubleUnet receives vgg19_weights=None so it does not
                # attempt a network download at construction time.  All
                # weights are supplied by the state_dict loaded below.
                if model_class is DoubleUnet:
                    model = model_class(vgg19_weights=None)
                else:
                    model = model_class()
                state_dict = torch.load(
                    ckpt_path,
                    map_location=resolved_device,
                    weights_only=True,
                )
                model.load_state_dict(state_dict)
                model.eval()
                model.to(resolved_device)
                self._models[key] = model
                logger.info(
                    "Loaded model %s from %s on %s",
                    key,
                    ckpt_path,
                    resolved_device,
                )
            except Exception:
                logger.warning(
                    "Failed to load model %s from %s",
                    key,
                    ckpt_path,
                    exc_info=True,
                )

        # Load YOLO separately via Ultralytics.
        yolo_path: Path = self._settings.MODEL_ROOT / _YOLO_SUBPATH
        if not yolo_path.exists():
            logger.warning(
                "YOLO checkpoint not found — two-stage pipeline unavailable. "
                "Expected: %s",
                yolo_path,
            )
        else:
            try:
                from ultralytics import YOLO

                self._yolo = YOLO(str(yolo_path))
                logger.info("Loaded YOLO from %s", yolo_path)
            except Exception:
                logger.warning(
                    "Failed to load YOLO from %s",
                    yolo_path,
                    exc_info=True,
                )

    # ------------------------------------------------------------------
    # Model retrieval
    # ------------------------------------------------------------------

    def get(self, pipeline_type: str, model_arch: str) -> nn.Module:
        """Return the loaded model for the given (pipeline_type, model_arch) pair.

        Args:
            pipeline_type: ``"single_stage"`` or ``"two_stage"``.
            model_arch: ``"unet"`` or ``"double_unet"``.

        Returns:
            The model in eval mode on the configured device.

        Raises:
            KeyError: If the combination was not loaded (checkpoint missing
                or unsupported arch for this pipeline).
        """
        key = f"{pipeline_type}/{model_arch}"
        if key not in self._models:
            raise KeyError(
                f"No model loaded for pipeline_type={pipeline_type!r}, "
                f"model_arch={model_arch!r} (key {key!r}). "
                "Check that the checkpoint file exists under MODEL_ROOT and "
                "was loaded at startup."
            )
        return self._models[key]

    def get_yolo(self) -> "YOLO":
        """Return the loaded Ultralytics YOLO model for tooth detection.

        Raises:
            RuntimeError: If YOLO weights were not found at startup.
        """
        if self._yolo is None:
            raise RuntimeError(
                "YOLO weights were not loaded at startup. "
                "Check that the YOLO checkpoint exists under MODEL_ROOT and "
                "verify the two-stage pipeline is available."
            )
        return self._yolo


# ==============================================================================
# Module-level singleton
# ==============================================================================
#
# Set by init_registry() during the FastAPI lifespan before any request
# arrives.  Import this in worker.py and pipeline modules so they always
# reference the same loaded-model store.

registry: ModelRegistry | None = None


def init_registry(settings: Settings) -> ModelRegistry:
    """Create and populate the module-level ``registry`` singleton.

    Called once from the FastAPI lifespan.  Subsequent calls (e.g. in
    tests) replace the existing registry.

    Args:
        settings: App settings used to locate checkpoints and select device.

    Returns:
        The initialised ``ModelRegistry`` instance.
    """
    global registry
    registry = ModelRegistry(settings)
    registry.load_all()
    return registry
