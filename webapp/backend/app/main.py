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

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, update

from app.core.config import get_settings
from app.core.database import get_session_factory, init_db
from app.core.exceptions import AppError
from app.core.security import hash_password
from app.inference.registry import init_registry
from app.models.job import Job, JobStatus
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)


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

    # Seed the bootstrap admin account on fresh deployments.  The seed step
    # runs only when BOTH seed vars are present AND the users table is empty,
    # so existing deployments are never affected by a restart.
    await _seed_admin(settings, session_factory)

    yield


# ---------------------------------------------------------------------------
# Seed helper
# ---------------------------------------------------------------------------


async def _seed_admin(settings, session_factory) -> None:  # type: ignore[type-arg]
    """Insert a bootstrap admin account when the users table is empty.

    The seed runs only when:
    1. Both ``SEED_ADMIN_USERNAME`` and ``SEED_ADMIN_PASSWORD`` are set.
    2. The ``users`` table currently contains zero rows.

    This means the seed is a no-op on every restart after the first user
    exists — whether that first user came from the seed itself or was
    created via the admin API.  There is no risk of duplicate inserts even
    if the same seed vars are kept in the environment indefinitely.

    The admin account starts with ``must_change_pw=False`` because a
    deployment owner who configured the seed vars already controls the
    credential — forcing a change on first boot would just add friction
    without security benefit.
    """
    if not settings.SEED_ADMIN_USERNAME or not settings.SEED_ADMIN_PASSWORD:
        # Seed vars not configured; nothing to do.
        return

    async with session_factory() as session:
        # Count existing users.  A single COUNT(*) is far cheaper than
        # loading any rows and avoids loading the full User relationship graph.
        count_result = await session.execute(select(func.count()).select_from(User))
        user_count = count_result.scalar_one()

        if user_count > 0:
            # At least one user already exists; skip seeding to avoid
            # creating a duplicate admin on every restart.
            return

        admin = User(
            username=settings.SEED_ADMIN_USERNAME,
            password_hash=hash_password(settings.SEED_ADMIN_PASSWORD),
            role=UserRole.admin,
            # The deployment owner configured these credentials intentionally,
            # so we do not force an immediate password change.
            must_change_pw=False,
        )
        session.add(admin)
        await session.commit()

    logger.info(
        "Seeded bootstrap admin account: username=%r",
        settings.SEED_ADMIN_USERNAME,
    )


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

    # ------------------------------------------------------------------
    # Exception handlers
    #
    # AppError extends HTTPException with a machine-readable ``code``
    # field.  Plain HTTPException raised by FastAPI's routing layer or
    # third-party middleware is intentionally NOT handled here so it
    # retains the default ``{"detail": ...}`` shape.
    # ------------------------------------------------------------------
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        """Serialise AppError instances as {code, detail} JSON.

        Called automatically by FastAPI when a route raises AppError.
        Returns an HTTP response with:
          - status code from ``exc.status_code``
          - JSON body: ``{"code": exc.code, "detail": exc.detail}``

        Plain HTTPException (from FastAPI internals or third-party middleware)
        is NOT handled here; it uses FastAPI's default handler which returns
        only ``{"detail": ...}``.

        Args:
            request: Incoming HTTP request (required by FastAPI handler
                contract; not used in this handler).
            exc: The AppError instance that was raised.

        Returns:
            JSONResponse with the error envelope.
        """
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "detail": exc.detail},
        )

    application.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]

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
