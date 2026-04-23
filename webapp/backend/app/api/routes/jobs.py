"""POST /api/jobs and GET /api/jobs/{job_id} route handlers."""

from __future__ import annotations

import uuid
from typing import Annotated

import cv2
import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import Settings, get_settings
from app.core.database import get_db, get_session_factory
from app.core.storage import StorageError, save_display_copy, save_upload
from app.inference.worker import run_inference
from app.models.image_result import ImageResult
from app.models.job import Job, JobStatus
from app.schemas.job import JobResponse, ModelArchField, PipelineTypeField

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
