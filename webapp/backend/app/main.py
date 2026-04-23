"""FastAPI application factory.

Phase 2 additions:
  - ``init_db()`` called in the lifespan so the async engine is ready
    before the first request arrives.
  - API router mounted at ``/api``.

Phase 3 additions:
  - ``init_registry()`` called in the lifespan to eagerly load all model
    checkpoints.  Startup fails fast (non-zero exit) if a required import
    is missing; missing checkpoint files log a WARNING instead.
  - Stale ``processing`` jobs are marked ``failed`` on startup so the
    UI doesn't hang if the backend restarted mid-inference.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update

from app.core.config import get_settings
from app.core.database import get_session_factory, init_db
from app.inference.registry import init_registry
from app.models.job import Job, JobStatus


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager.

    Startup:
      1. Initialise the async database engine from ``Settings.DATABASE_URL``.
      2. Load all model checkpoints into the ``ModelRegistry`` singleton.
         Missing checkpoint files are logged as WARNINGs (not errors) so the
         app starts with a partial model set.
      3. Mark any ``processing`` jobs as ``failed`` — these were in-flight
         when the backend last restarted and will never complete.

    Shutdown:
      No-op — Python GC releases model tensors.
    """
    settings = get_settings()
    init_db(settings.DATABASE_URL)

    # Load model checkpoints eagerly so the first inference request does not
    # incur a cold-start penalty.  init_registry logs a warning per missing
    # checkpoint rather than raising.
    init_registry(settings)

    # Recover from a mid-inference backend restart: any job still in
    # "processing" state is now permanently stuck because the background
    # task was lost.  Mark them failed so the frontend can show an error.
    session_factory = get_session_factory()
    async with session_factory() as session:
        await session.execute(
            update(Job)
            .where(Job.status == JobStatus.processing)
            .values(
                status=JobStatus.failed,
                error_message=(
                    "Backend restarted while this job was in progress. "
                    "Please resubmit."
                ),
            )
        )
        await session.commit()

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
