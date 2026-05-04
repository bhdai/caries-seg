"""API router package.

Aggregates all route sub-routers and exports a single ``router`` instance
that is mounted under the ``/api`` prefix in ``app/main.py``.
"""

from fastapi import APIRouter

from app.api.routes import admin, auth, files, jobs, patients

router = APIRouter()
router.include_router(auth.router, tags=["auth"])
router.include_router(jobs.router, tags=["jobs"])
router.include_router(files.router, tags=["files"])
router.include_router(admin.router, tags=["admin"])
router.include_router(patients.router, tags=["patients"])
