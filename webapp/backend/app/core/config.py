"""Application settings loaded from environment variables.

All backend configuration is centralised here so that no other module
reads ``os.environ`` directly.  Pydantic-settings validates types at
import time; a missing required variable causes an immediate, descriptive
startup error rather than a cryptic ``KeyError`` at call time.
"""

from __future__ import annotations

from functools import cached_property, lru_cache
from pathlib import Path
from typing import Optional

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
    # Authentication — JWT
    # ------------------------------------------------------------------
    # Secret key used to sign JWTs.  Must be set in production; a missing
    # value causes an immediate startup error so misconfigured deployments
    # fail loudly rather than accepting unsigned tokens.
    JWT_SECRET: str

    # HMAC algorithm used to sign tokens.  HS256 is the standard symmetric
    # choice for single-server deployments.
    JWT_ALGORITHM: str = "HS256"

    # Session lifetime in hours.  8 hours matches a typical clinical shift,
    # so staff are not forced to re-login mid-day but sessions do not persist
    # overnight by default.
    JWT_EXPIRY_HOURS: int = 8

    # ------------------------------------------------------------------
    # Authentication — Cookie
    # ------------------------------------------------------------------
    # Whether to set the Secure flag on the auth cookie.  Should be True
    # in production (HTTPS) and False for local HTTP development.
    COOKIE_SECURE: bool = False

    # Optional domain attribute for the auth cookie.  Leave unset (None)
    # for single-domain deployments; set to ".example.com" to share the
    # cookie across subdomains.
    COOKIE_DOMAIN: Optional[str] = None

    # ------------------------------------------------------------------
    # Seed admin
    # ------------------------------------------------------------------
    # When both vars are present and the users table is empty, the lifespan
    # handler inserts a bootstrap admin account so the application is
    # immediately usable after a fresh deployment.  Once any user exists the
    # seed step is skipped on subsequent restarts.
    SEED_ADMIN_USERNAME: Optional[str] = None
    SEED_ADMIN_PASSWORD: Optional[str] = None

    # ------------------------------------------------------------------
    # Google OAuth2
    # ------------------------------------------------------------------
    # All three vars are optional.  When GOOGLE_CLIENT_ID is None the
    # /api/auth/google and /api/auth/google/callback endpoints return 404
    # so deployments without Google OAuth are unaffected.
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    # Full URL that Google will redirect back to after user consent, e.g.
    # "http://localhost:8000/api/auth/google/callback" for local dev or
    # "https://example.com/api/auth/google/callback" in production.
    GOOGLE_REDIRECT_URI: Optional[str] = None

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
