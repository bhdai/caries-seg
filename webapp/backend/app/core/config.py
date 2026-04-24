"""Application settings loaded from environment variables.

All backend configuration is centralised here so that no other module
reads ``os.environ`` directly.  Pydantic-settings validates types at
import time; a missing required variable causes an immediate, descriptive
startup error rather than a cryptic ``KeyError`` at call time.
"""

from __future__ import annotations

from functools import cached_property, lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Read from .env when running outside Docker (e.g. local development).
        env_file=".env",
        env_file_encoding="utf-8",
        # Allow extra fields so the same .env works for both backend and
        # docker-compose without causing validation errors.
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    DATABASE_URL: str

    # ------------------------------------------------------------------
    # File storage
    # ------------------------------------------------------------------
    # Root of the storage volume.  Subdirectories uploads/, masks/, and
    # display/ are created under this path at startup if absent.
    STORAGE_ROOT: Path

    # Root of the model checkpoint directory (bind-mounted from files/).
    MODEL_ROOT: Path

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------
    # Maximum pixels on the longest edge for display copies.  Keeps the
    # browser canvas responsive for very high-resolution panoramics.
    MAX_DISPLAY_PX: int = 1600

    # PyTorch device selection.  "auto" prefers CUDA when available and
    # falls back to CPU otherwise.
    DEVICE: str = "auto"

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @field_validator("DEVICE")
    @classmethod
    def _validate_device(cls, v: str) -> str:
        assert v in {"auto", "cpu", "cuda"}, (
            f"DEVICE must be 'auto', 'cpu', or 'cuda', got {v!r}"
        )
        return v

    @field_validator("MAX_DISPLAY_PX")
    @classmethod
    def _validate_max_display_px(cls, v: int) -> int:
        assert v > 0, "MAX_DISPLAY_PX must be a positive integer"
        return v

    @cached_property
    def resolved_device(self) -> str:
        """Resolve the effective inference device for this process.

        ``DEVICE=auto`` prefers CUDA when a CUDA-capable Torch runtime is
        available.  ``DEVICE=cuda`` fails fast when CUDA is unavailable so the
        process does not silently fall back to CPU and surprise operators.
        """
        if self.DEVICE == "cpu":
            return "cpu"

        import torch

        cuda_available = torch.cuda.is_available()
        if self.DEVICE == "auto":
            return "cuda" if cuda_available else "cpu"

        assert cuda_available, (
            "DEVICE='cuda' requires a CUDA-enabled Torch build and an "
            "available GPU"
        )
        return "cuda"


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings.

    Uses ``functools.lru_cache`` so that settings are loaded from the
    environment exactly once per process lifetime.  Tests override this
    dependency via ``app.dependency_overrides`` to inject test-specific
    values without touching the environment.
    """
    return Settings()  # type: ignore[call-arg]
