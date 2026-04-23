"""GET /api/files/{image_result_id}/original and
   GET /api/files/{image_result_id}/mask route handlers.

Both endpoints look up the ``ImageResult`` row, resolve the stored path,
and stream the file with ``FileResponse``.  They return 404 when:

- No ``ImageResult`` with the given ID exists.
- The path column is ``None`` (display copy or mask not yet produced).
- The file does not exist on disk (e.g. volume was reset).
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.models.image_result import ImageResult

router = APIRouter(prefix="/files")


async def _get_image_result(
    image_result_id: uuid.UUID,
    db: AsyncSession,
) -> ImageResult:
    """Fetch an ImageResult row or raise 404."""
    result = await db.execute(
        select(ImageResult).where(ImageResult.id == image_result_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"ImageResult {image_result_id} not found.",
        )
    return row


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
        raise HTTPException(
            status_code=404,
            detail=f"{label} has not been produced yet for this image result.",
        )
    path = Path(path_str)
    if not path.exists():
        raise HTTPException(
            status_code=404,
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
) -> FileResponse:
    """Stream the display-resized copy of the uploaded image.

    Returns:
        PNG file with ``Content-Type: image/png``.

    Raises:
        HTTPException 404: Image result or display copy not found.
    """
    row = await _get_image_result(image_result_id, db)
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
) -> FileResponse:
    """Stream the binary caries segmentation mask.

    Returns:
        PNG file with ``Content-Type: image/png``.

    Raises:
        HTTPException 404: Image result or mask not found.
    """
    row = await _get_image_result(image_result_id, db)
    path = _resolve_file(row.mask_path, "Mask")
    return FileResponse(
        path=str(path),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )
