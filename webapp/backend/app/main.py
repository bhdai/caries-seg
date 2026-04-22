"""FastAPI application factory.

Phase 1 — skeleton only:
  - Lifespan context manager (startup / shutdown hooks; inference wiring
    is added in Phase 3).
  - ``GET /health`` endpoint for Docker health checks and service readiness.
  - API router placeholder (routes are mounted in Phase 2).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager.

    Startup:
      Phase 3 will add model loading and stale-job cleanup here.

    Shutdown:
      No-op — Python GC releases model tensors.
    """
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

    # TODO (Phase 2): mount the API router here.
    #   from app.api.routes import router
    #   application.include_router(router, prefix="/api")

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
