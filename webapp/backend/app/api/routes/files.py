"""GET /api/files/{image_result_id}/original and
   GET /api/files/{image_result_id}/mask route handlers.

Both endpoints look up the ``ImageResult`` row, resolve the stored path,
and stream the file with ``FileResponse``.  They return 404 when:

- No ``ImageResult`` with the given ID exists.
- The path column is ``None`` (display copy or mask not yet produced).
- The file does not exist on disk (e.g. volume was reset).

Ownership is enforced: non-admin users may only retrieve files for jobs
they own.  Orphaned jobs (owner_id=None) are accessible only to admins.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.core.exceptions import AppError
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.image_result import ImageResult
from app.models.job import Job
from app.models.user import User

# Applying get_current_user at the router level rejects unauthenticated callers
# before any handler runs.  Individual handlers inject the user instance to
# perform the ownership check.
router = APIRouter(prefix="/files", dependencies=[Depends(get_current_user)])


async def _get_image_result(
    image_result_id: uuid.UUID,
    db: AsyncSession,
    current_user: User,
) -> ImageResult:
    """Fetch an ImageResult row (with its parent Job) or raise 404/403.

    Loads the parent Job via a join so the ownership check is a single round-
    trip rather than two separate selects.  Raises 403 (not 404) when the row
    exists but the caller does not own it so that the error message is
    actionable without leaking the existence of other users' data.
    """
    # Join ImageResult → Job in one query to get both rows at once.
    result = await db.execute(
        select(ImageResult, Job)
        .join(Job, Job.id == ImageResult.job_id)
        .where(ImageResult.id == image_result_id)
    )
    row = result.one_or_none()
    if row is None:
        raise AppError(
            status_code=404,
            code="files.notFound",
            detail=f"ImageResult {image_result_id} not found.",
        )
    image_result, job = row

    # Admins see all files; regular users see only their own jobs.  Orphaned
    # jobs (owner_id=None) are visible only to admins.
    if current_user.role != "admin" and job.owner_id != current_user.id:
        raise AppError(status_code=403, code="files.accessDenied", detail="Access denied.")

    return image_result


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
        raise AppError(
            status_code=409,
            code="files.notReady",
            detail=f"{label} has not been produced yet for this image result.",
        )
    path = Path(path_str)
    if not path.exists():
        raise AppError(
            status_code=500,
            code="files.missingOnDisk",
            detail=f"{label} file not found on disk.",
        )
    return path


# ---------------------------------------------------------------------------
# GET /api/files/{image_result_id}/original
# ---------------------------------------------------------------------------


@router.get("/{image_result_id}/original")
async def get_original(
    image_result_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Stream the display-resized copy of the uploaded image.

    Returns:
        PNG file with ``Content-Type: image/png``.

    Raises:
        HTTPException 403: Caller does not own the job.
        HTTPException 404: Image result or display copy not found.
    """
    row = await _get_image_result(image_result_id, db, current_user)
    path = _resolve_file(row.display_path, "Display copy")
    return FileResponse(
        path=str(path),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# ---------------------------------------------------------------------------
# GET /api/files/{image_result_id}/mask
# ---------------------------------------------------------------------------


@router.get("/{image_result_id}/mask")
async def get_mask(
    image_result_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    """Stream the binary caries segmentation mask.

    Returns:
        PNG file with ``Content-Type: image/png``.

    Raises:
        HTTPException 403: Caller does not own the job.
        HTTPException 404: Image result or mask not found.
    """
    row = await _get_image_result(image_result_id, db, current_user)
    path = _resolve_file(row.mask_path, "Mask")
    return FileResponse(
        path=str(path),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )
