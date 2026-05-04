"""Route handlers for share link management and public result access.

Authenticated endpoints
-----------------------
POST   /api/share-links                       Create or return existing active link.
GET    /api/share-links/by-job/{job_id}       Get active link for a specific job.
DELETE /api/share-links/{share_link_id}       Revoke (delete) a share link.

Public endpoints (no auth required)
------------------------------------
GET    /api/shared/{token}                              Return public result JSON.
GET    /api/shared/{token}/files/{image_result_id}/original   Stream original image.
GET    /api/shared/{token}/files/{image_result_id}/mask       Stream mask image.

Rate limiting
-------------
The three public endpoints are limited to 30 requests per minute per IP via
the ``slowapi`` ``Limiter`` instance configured in ``app/main.py``.  The
``request`` parameter on each public handler is required by slowapi to extract
the client IP even though it is not used directly in handler logic.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.share_link import (
    CreateShareLinkRequest,
    ShareLinkResponse,
    SharedResultResponse,
)
import app.services.share_links as share_links_service

# ---------------------------------------------------------------------------
# Rate limiter (configured on the FastAPI app in main.py)
# ---------------------------------------------------------------------------

# The Limiter instance is created in main.py and stored in app.state so that
# it can be referenced here without creating a circular import.  slowapi
# discovers the limiter via the ``request.app.state.limiter`` attribute when
# the ``@limiter.limit(...)`` decorator calls ``_check_request_limit``.
#
# We import get_limiter lazily inside each public handler to keep the import
# graph clean and to allow tests that don't configure slowapi to skip the
# rate-limit check via the usual dependency-override mechanism.
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# ==============================================================================
# Authenticated router — all routes require a logged-in user
# ==============================================================================

router = APIRouter(
    prefix="/share-links",
    dependencies=[Depends(get_current_user)],
)


# ---------------------------------------------------------------------------
# POST /api/share-links
# ---------------------------------------------------------------------------


@router.post("", status_code=201, response_model=ShareLinkResponse)
async def create_share_link(
    body: CreateShareLinkRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ShareLinkResponse:
    """Create a share link for the given job, or return the existing active one.

    The operation is idempotent: POSTing the same ``job_id`` twice without
    revoking in between returns the same link, preventing duplicate rows.

    Returns:
        HTTP 201 with a ``ShareLinkResponse`` containing the shareable URL.

    Raises:
        HTTPException 404: Job not found.
        HTTPException 403: Caller does not own the job (non-admin).
    """
    return await share_links_service.create_share_link(
        job_id=body.job_id,
        expires_in_days=body.expires_in_days,
        user=current_user,
        db=db,
        settings=settings,
    )


# ---------------------------------------------------------------------------
# GET /api/share-links/by-job/{job_id}
# ---------------------------------------------------------------------------


@router.get("/by-job/{job_id}", response_model=ShareLinkResponse | None)
async def get_share_link_for_job(
    job_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ShareLinkResponse | None:
    """Return the active share link for a job, or null if none exists.

    Returns:
        ``ShareLinkResponse`` if an active link exists, ``null`` otherwise.

    Raises:
        HTTPException 404: Job not found.
        HTTPException 403: Caller does not own the job (non-admin).
    """
    return await share_links_service.get_share_link_for_job(
        job_id=job_id,
        user=current_user,
        db=db,
        settings=settings,
    )


# ---------------------------------------------------------------------------
# DELETE /api/share-links/{share_link_id}
# ---------------------------------------------------------------------------


@router.delete("/{share_link_id}", status_code=204)
async def revoke_share_link(
    share_link_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Revoke a share link, immediately invalidating the public token.

    Returns:
        HTTP 204 No Content on success.

    Raises:
        HTTPException 404: Share link not found.
        HTTPException 403: Caller does not own the linked job (non-admin).
    """
    await share_links_service.revoke_share_link(
        share_link_id=share_link_id,
        user=current_user,
        db=db,
    )


# ==============================================================================
# Public router — NO authentication dependency
# ==============================================================================

public_router = APIRouter(prefix="/shared")


def _resolve_file(path_str: str | None, label: str) -> Path:
    """Resolve a stored path string to a ``Path``, raising 404 if unavailable.

    Args:
        path_str: Value from the database column; ``None`` means the file
            has not been produced yet.
        label: Human-readable label for the file kind used in error messages.

    Returns:
        Resolved ``Path`` that exists on disk.

    Raises:
        HTTPException 404: Path is ``None`` or file does not exist on disk.
    """
    if path_str is None:
        raise HTTPException(status_code=404, detail=f"{label} not available yet.")
    path = Path(path_str)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{label} not found on disk.")
    return path


# ---------------------------------------------------------------------------
# GET /api/shared/{token}
# ---------------------------------------------------------------------------


@public_router.get("/{token}", response_model=SharedResultResponse)
@limiter.limit("30/minute")
async def get_public_result(
    token: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SharedResultResponse:
    """Return the inference results for a shared job, without authentication.

    Returns:
        HTTP 200 with a ``SharedResultResponse`` containing patient name,
        scan date, and image summaries.

    Raises:
        HTTPException 404: Token not found or revoked.
        HTTPException 410: Token has expired.
        HTTPException 429: Rate limit exceeded (30 req/min per IP).
    """
    return await share_links_service.get_public_result(token=token, db=db)


# ---------------------------------------------------------------------------
# GET /api/shared/{token}/files/{image_result_id}/original
# ---------------------------------------------------------------------------


@public_router.get("/{token}/files/{image_result_id}/original")
@limiter.limit("30/minute")
async def get_public_original(
    token: str,
    image_result_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FileResponse:
    """Stream the display copy of an image via a public share token.

    Returns:
        PNG file response for the display-resized image.

    Raises:
        HTTPException 404: Token not found, revoked, or display copy missing.
        HTTPException 410: Token expired.
        HTTPException 403: Image belongs to a different job than the token.
        HTTPException 429: Rate limit exceeded.
    """
    _link, image_result = await share_links_service.get_public_image_result(
        token=token, image_result_id=image_result_id, db=db
    )
    path = _resolve_file(image_result.display_path, "Display copy")
    return FileResponse(
        path=str(path),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# ---------------------------------------------------------------------------
# GET /api/shared/{token}/files/{image_result_id}/mask
# ---------------------------------------------------------------------------


@public_router.get("/{token}/files/{image_result_id}/mask")
@limiter.limit("30/minute")
async def get_public_mask(
    token: str,
    image_result_id: uuid.UUID,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FileResponse:
    """Stream the inference mask image via a public share token.

    Returns:
        PNG file response for the segmentation mask.

    Raises:
        HTTPException 404: Token not found, revoked, or mask not yet ready.
        HTTPException 410: Token expired.
        HTTPException 403: Image belongs to a different job than the token.
        HTTPException 429: Rate limit exceeded.
    """
    _link, image_result = await share_links_service.get_public_image_result(
        token=token, image_result_id=image_result_id, db=db
    )
    path = _resolve_file(image_result.mask_path, "Mask")
    return FileResponse(
        path=str(path),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )
