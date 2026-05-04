"""API router package.

Aggregates all route sub-routers and exports a single ``router`` instance
that is mounted under the ``/api`` prefix in ``app/main.py``.

The ``share.public_router`` is included here alongside the authenticated
``share.router`` so that all share-related paths live under ``/api``.
Public endpoints carry no auth dependency; the ``/api`` prefix alone does
not imply authentication.
"""

from fastapi import APIRouter

from app.api.routes import admin, auth, files, jobs, patients, share

router = APIRouter()
router.include_router(auth.router, tags=["auth"])
router.include_router(jobs.router, tags=["jobs"])
router.include_router(files.router, tags=["files"])
router.include_router(admin.router, tags=["admin"])
router.include_router(patients.router, tags=["patients"])
# Authenticated share-link management (create, get, revoke).
router.include_router(share.router, tags=["share-links"])
# Public result access — no auth dependency, rate-limited via slowapi.
router.include_router(share.public_router, tags=["shared"])
