"""Application settings loaded from environment variables.

All backend configuration is centralised here so that no other module
reads ``os.environ`` directly.  Pydantic-settings validates types at
import time; a missing required variable causes an immediate, descriptive
startup error rather than a cryptic ``KeyError`` at call time.
"""

from __future__ import annotations

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

    # PyTorch device string.  Defaults to "cpu"; override to "cuda" if
    # the host has an NVIDIA GPU and the Docker NVIDIA runtime is active.
    DEVICE: str = "cpu"

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @field_validator("DEVICE")
    @classmethod
    def _validate_device(cls, v: str) -> str:
        assert v in {"cpu", "cuda"}, f"DEVICE must be 'cpu' or 'cuda', got {v!r}"
        return v

    @field_validator("MAX_DISPLAY_PX")
    @classmethod
    def _validate_max_display_px(cls, v: int) -> int:
        assert v > 0, "MAX_DISPLAY_PX must be a positive integer"
        return v


# Module-level singleton — imported by all other modules as:
#   from app.core.config import settings
settings = Settings()  # type: ignore[call-arg]
