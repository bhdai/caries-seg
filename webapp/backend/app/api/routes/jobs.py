"""Route handlers for all job-related endpoints.

Endpoints
---------
POST   /api/jobs                      Create a new inference job.
GET    /api/jobs                      List jobs (paginated, filterable).
GET    /api/jobs/{job_id}             Full job detail for a single job.
POST   /api/jobs/{job_id}/rerun       Server-side rerun from stored uploads.
"""

from __future__ import annotations

import uuid
from typing import Annotated

import cv2
import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import Settings, get_settings
from app.core.database import get_db, get_session_factory
from app.core.storage import StorageError, save_display_copy, save_upload
from app.inference.worker import run_inference
from app.models.image_result import ImageResult
from app.models.job import Job, JobStatus
from app.schemas.job import JobResponse, ModelArchField, PipelineTypeField
from app.schemas.job_history import (
    JobListQuery,
    JobsPageResponse,
    ModelFilter,
    PipelineFilter,
    SortOrder,
    StatusFilter,
)
import app.services.jobs as jobs_service

router = APIRouter(prefix="/jobs")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum accepted file size for a single upload.  Files larger than this
# are rejected before being written to disk to avoid filling the storage
# volume with oversized payloads.
_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB

_ALLOWED_MIME_TYPES = {"image/jpeg", "image/png"}


# ---------------------------------------------------------------------------
# POST /api/jobs
# ---------------------------------------------------------------------------


@router.post("", status_code=202, response_model=JobResponse)
async def create_job(
    files: Annotated[
        list[UploadFile],
        File(description="One or more panoramic X-ray images (JPEG or PNG)."),
    ],
    pipeline_type: Annotated[PipelineTypeField, Form()],
    model_arch: Annotated[ModelArchField, Form()],
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> JobResponse:
    """Accept an inference job submission.

    Validates uploaded files (size, MIME type), writes them to the storage
    volume, creates ``Job`` and ``ImageResult`` rows, and enqueues the
    inference background task.

    Returns:
        HTTP 202 with the full ``JobResponse`` payload (status=``"pending"``).

    Raises:
        HTTPException 413: Any file exceeds 10 MB.
        HTTPException 422: Any file has a disallowed MIME type or cannot
            be decoded as a valid image.
    """
    # ------------------------------------------------------------------
    # Phase 1 — validate all files before touching the database or disk.
    #
    # We buffer every file's bytes here so we can reject the entire
    # request up-front if any file is invalid.  The 10 MB cap keeps
    # peak memory usage bounded.
    # ------------------------------------------------------------------
    validated: list[dict] = []
    for upload in files:
        content = await upload.read()

        if len(content) > _MAX_FILE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"{upload.filename!r} exceeds the 10 MB upload limit "
                    f"({len(content) // (1024 * 1024)} MB received)."
                ),
            )

        if upload.content_type not in _ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{upload.filename!r} has unsupported content type "
                    f"{upload.content_type!r}. Only image/jpeg and "
                    "image/png are accepted."
                ),
            )

        # Decode to confirm the file is a valid image and to read its
        # spatial dimensions for the original_size field.
        nparr = np.frombuffer(content, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(
                status_code=422,
                detail=f"{upload.filename!r} could not be decoded as an image.",
            )

        validated.append(
            {
                "upload": upload,
                "content": content,
                "img": img,
            }
        )

    # ------------------------------------------------------------------
    # Phase 2 — persist the job and image results.
    # ------------------------------------------------------------------
    job_id = uuid.uuid4()
    job = Job(
        id=job_id,
        status=JobStatus.pending,
        pipeline_type=pipeline_type,
        model_arch=model_arch,
    )
    db.add(job)

    for item in validated:
        upload: UploadFile = item["upload"]
        content: bytes = item["content"]
        img_bgr: np.ndarray = item["img"]

        result_id = uuid.uuid4()
        h, w = img_bgr.shape[:2]

        try:
            # Save the raw upload bytes.
            upload_path = save_upload(
                content=content,
                filename=upload.filename or "upload.bin",
                job_id=job_id,
                settings=settings,
            )

            # Save a display-resized copy so the file-serving endpoint has
            # something to serve even before mask inference runs.
            img_float = img_bgr.astype(np.float32) / 255.0
            display_path = save_display_copy(
                img=img_float,
                image_result_id=result_id,
                settings=settings,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        except StorageError as e:
            raise HTTPException(
                status_code=500,
                detail="Failed to persist uploaded files.",
            ) from e

        image_result = ImageResult(
            id=result_id,
            job_id=job_id,
            original_filename=upload.filename or "upload.bin",
            upload_path=str(upload_path),
            display_path=str(display_path),
            original_size={"width": w, "height": h},
        )
        db.add(image_result)

    # Commit now — before enqueueing the background task — so that the job
    # and image_result rows are visible in the database when run_inference
    # opens its own session.  FastAPI BackgroundTasks execute after the
    # response is sent but before yield-dependency teardown, so without
    # this explicit commit the background task would race against the
    # get_db cleanup commit and see no rows.
    await db.commit()
    await db.refresh(job)

    # Enqueue the inference background task.  The task opens its own DB
    # session so it is decoupled from this request's transaction.
    background_tasks.add_task(run_inference, job_id, get_session_factory())

    return JobResponse.model_validate(job)


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}
# ---------------------------------------------------------------------------


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID, db: Annotated[AsyncSession, Depends(get_db)]
) -> JobResponse:
    """Return the full job payload including all image results.

    Raises:
        HTTPException 404: No job with the given ID exists.
    """
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    return JobResponse.model_validate(job)


# ---------------------------------------------------------------------------
# GET /api/jobs  (list with filters and pagination)
# ---------------------------------------------------------------------------


def _parse_list_query(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Annotated[StatusFilter, Query()] = "all",
    pipeline_type: Annotated[PipelineFilter, Query()] = "all",
    model_arch: Annotated[ModelFilter, Query()] = "all",
    search: Annotated[str | None, Query(max_length=200)] = None,
    sort: Annotated[SortOrder, Query()] = "last_activity_desc",
) -> JobListQuery:
    """Construct a validated ``JobListQuery`` from individual query parameters.

    Defined as a dependency factory so FastAPI surfaces each parameter in
    the OpenAPI schema and validates enum membership before the handler runs.
    """
    return JobListQuery(
        page=page,
        page_size=page_size,
        status=status,
        pipeline_type=pipeline_type,
        model_arch=model_arch,
        search=search,
        sort=sort,
    )


@router.get("", response_model=JobsPageResponse)
async def list_jobs(
    query: Annotated[JobListQuery, Depends(_parse_list_query)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobsPageResponse:
    """Return a paginated, filterable list of job summaries.

    Supports filtering by status, pipeline type, and model architecture,
    free-text search across job IDs and image filenames, and three sort
    orders.  Results are always newest-first within each sort variant's
    tie-breaker rules to keep pagination stable.

    Query parameters
    ----------------
    page         : 1-based page number (default 1).
    page_size    : Items per page, 1–100 (default 20).
    status       : One of pending | processing | completed | failed | all.
    pipeline_type: One of single_stage | two_stage | all.
    model_arch   : One of unet | double_unet | all.
    search       : Free-text match against job ID or image filenames.
    sort         : newest | oldest | last_activity_desc (default).
    """
    return await jobs_service.list_jobs(query, db)


# ---------------------------------------------------------------------------
# POST /api/jobs/{job_id}/rerun
# ---------------------------------------------------------------------------


@router.post("/{job_id}/rerun", status_code=202, response_model=JobResponse)
async def rerun_job(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> JobResponse:
    """Create a new pending job by reusing an existing job's stored uploads.

    Verifies that all source upload files still exist on disk before
    committing any new rows, then copies inputs into a fresh job namespace
    and enqueues inference.

    Returns:
        HTTP 202 with the full ``JobResponse`` for the new pending job.

    Raises:
        HTTPException 404: Source job does not exist.
        HTTPException 409: Source job has no image results, or one or more
            upload files are no longer available on disk.
        HTTPException 422: A source file cannot be decoded as a valid image.
        HTTPException 500: Unexpected storage error while copying files.
    """
    return await jobs_service.rerun_job(job_id, db, settings, background_tasks)
