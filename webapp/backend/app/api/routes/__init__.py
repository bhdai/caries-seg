"""API router package.

Aggregates all route sub-routers and exports a single ``router`` instance
that is mounted under the ``/api`` prefix in ``app/main.py``.
"""

from fastapi import APIRouter

from app.api.routes import files, jobs

router = APIRouter()
router.include_router(jobs.router, tags=["jobs"])
router.include_router(files.router, tags=["files"])
