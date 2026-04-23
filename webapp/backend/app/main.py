"""FastAPI application factory.

Phase 2 additions:
  - ``init_db()`` called in the lifespan so the async engine is ready
    before the first request arrives.
  - API router mounted at ``/api``.

Phase 3 will add model loading and stale-job cleanup to the lifespan.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager.

    Startup:
      1. Initialise the async database engine from ``Settings.DATABASE_URL``.
      2. TODO (Phase 3): load ModelRegistry and mark stale processing jobs
         as ``failed``.

    Shutdown:
      No-op — Python GC releases model tensors.
    """
    settings = get_settings()
    init_db(settings.DATABASE_URL)
    # TODO (Phase 3): load ModelRegistry and mark stale processing jobs failed.
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="Caries Segmentation API",
        description="Inference API for panoramic dental X-ray caries segmentation.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # CORS
    #
    # The Vite dev server runs on a different port than the backend, so
    # we allow localhost origins in development.  Tighten this for
    # production by listing the exact frontend origin.
    # ------------------------------------------------------------------
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from app.api.routes import router

    application.include_router(router, prefix="/api")

    return application


app = create_app()


# ---------------------------------------------------------------------------
# Health endpoint
#
# Kept at the top level (not under /api) so that Docker healthchecks and
# load-balancer probes reach it without authentication middleware.
# ---------------------------------------------------------------------------
@app.get("/health", tags=["ops"])
async def health_check() -> dict[str, str]:
    """Return a simple liveness signal."""
    return {"status": "ok"}
