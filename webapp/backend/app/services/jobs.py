"""Service layer for job history list and rerun orchestration.

Provides the canonical query logic for history and dashboard surfaces, and
the server-side rerun flow that clones a prior job's stored uploads into a
new pending job.

These functions contain all database and storage orchestration so that route
handlers stay thin HTTP-boundary translators.

Circular-import note
--------------------
``rerun_job`` imports ``run_inference`` from ``app.inference.worker`` inside
the function body (not at module level) so that ``worker.py`` can safely
import ``touch_job_activity`` from this module without creating a cycle.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import get_session_factory
from app.core.storage import StorageError, save_display_copy, save_upload
from app.models.image_result import ImageResult
from app.models.job import Job, JobStatus
from app.schemas.job import JobResponse
from app.schemas.job_history import JobListQuery, JobSummaryResponse, JobsPageResponse

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Activity timestamp helper
# ---------------------------------------------------------------------------


def touch_job_activity(job: Job, when: datetime | None = None) -> None:
    """Update the job's activity timestamp whenever meaningful progress occurs
    so dashboard and history labels reflect actual execution progress rather
    than only initial creation time.

    Args:
        job: The ORM Job instance whose ``updated_at`` timestamp should be
            refreshed.
        when: The timestamp to record; defaults to the current UTC time if
            not provided.
    """
    if when is None:
        when = datetime.now(tz=timezone.utc)
    job.updated_at = when


# ---------------------------------------------------------------------------
# List query
# ---------------------------------------------------------------------------


async def list_jobs(query: JobListQuery, db: AsyncSession) -> JobsPageResponse:
    """Execute the canonical history query.

    Apply filters, search, stable sorting, and pagination against jobs-first
    records; aggregate lightweight filename preview data; and return a compact
    page model for dashboard/history consumers.

    Args:
        query: Normalized filter, sort, and pagination parameters.
        db: Active async database session.

    Returns:
        A single page of job summaries with pagination metadata.
    """
    # ==============================================================================
    # Build the set of WHERE conditions for both the count and page queries.
    #
    # Conditions are collected into a list and applied uniformly to both
    # select(func.count(...)) and select(Job) so the two queries stay in sync
    # without duplicating filter logic.
    # ==============================================================================
    filters = []

    if query.status != "all":
        filters.append(Job.status == query.status)
    if query.pipeline_type != "all":
        filters.append(Job.pipeline_type == query.pipeline_type)
    if query.model_arch != "all":
        filters.append(Job.model_arch == query.model_arch)

    if query.search:
        # Match against the string form of the job UUID and against every
        # filename stored under that job.  The filename branch is expressed as
        # an IN subquery that projects back to unique job IDs, preventing the
        # fan-out that a direct JOIN would introduce when one job has multiple
        # matching files.
        #
        # Escape SQL wildcard characters in the user-supplied search text so
        # that literal underscores and percent signs in filenames (e.g.
        # "alpha_2.png") are matched exactly and cannot act as ILIKE pattern
        # wildcards.  We use backslash as the escape character, which requires
        # escaping any literal backslashes first.
        _ILIKE_ESCAPE = "\\"
        safe_search = (
            query.search
            .replace(_ILIKE_ESCAPE, _ILIKE_ESCAPE * 2)  # escape literal \
            .replace("%", f"{_ILIKE_ESCAPE}%")           # escape wildcard %
            .replace("_", f"{_ILIKE_ESCAPE}_")           # escape wildcard _
        )
        search_term = f"%{safe_search}%"
        filename_job_ids = (
            select(ImageResult.job_id)
            .where(ImageResult.original_filename.ilike(search_term, escape=_ILIKE_ESCAPE))
            .scalar_subquery()
        )
        filters.append(
            or_(
                cast(Job.id, String).ilike(search_term, escape=_ILIKE_ESCAPE),
                Job.id.in_(filename_job_ids),
            )
        )

    # ==============================================================================
    # Count total matching jobs before applying pagination.
    # ==============================================================================
    count_q = select(func.count(Job.id))
    for f in filters:
        count_q = count_q.where(f)
    total_items: int = (await db.execute(count_q)).scalar_one()

    # ==============================================================================
    # Build the page query with stable sort order.
    #
    # Every sort variant includes tie-breakers (created_at, then id) so
    # pagination is consistent across requests even when the primary column
    # has equal values across multiple jobs.
    # ==============================================================================
    q = select(Job)
    for f in filters:
        q = q.where(f)

    if query.sort == "oldest":
        q = q.order_by(Job.created_at.asc(), Job.id.asc())
    elif query.sort == "newest":
        q = q.order_by(Job.created_at.desc(), Job.id.desc())
    else:
        # last_activity_desc (default): most recently active jobs first.
        q = q.order_by(Job.updated_at.desc(), Job.created_at.desc(), Job.id.desc())

    # ==============================================================================
    # Apply pagination.
    # ==============================================================================
    offset = (query.page - 1) * query.page_size
    q = q.offset(offset).limit(query.page_size)

    # Execute the page query.  The Job model configures lazy="selectin" on
    # image_results, so SQLAlchemy issues a single secondary SELECT IN query
    # for all jobs on the page — two round-trips total, both bounded by page_size.
    result = await db.execute(q)
    jobs = list(result.scalars().all())

    # ==============================================================================
    # Map ORM objects to compact summary DTOs.
    # ==============================================================================
    items = [_job_to_summary(job) for job in jobs]

    total_pages = math.ceil(total_items / query.page_size) if total_items > 0 else 0

    return JobsPageResponse(
        items=items,
        page=query.page,
        page_size=query.page_size,
        total_items=total_items,
        total_pages=total_pages,
        has_previous_page=query.page > 1,
        has_next_page=query.page < total_pages,
    )


def _job_to_summary(job: Job) -> JobSummaryResponse:
    """Map a Job ORM object (with pre-loaded image_results) to a compact summary DTO.

    The filename_preview is capped at three entries to keep list payloads
    bounded regardless of how many images a job contains.
    """
    filenames = [ir.original_filename for ir in job.image_results]
    return JobSummaryResponse(
        id=job.id,
        status=job.status,
        pipeline_type=job.pipeline_type,
        model_arch=job.model_arch,
        created_at=job.created_at,
        last_activity_at=job.updated_at,
        image_count=len(job.image_results),
        primary_filename=filenames[0] if filenames else "",
        filename_preview=filenames[:3],
        error_message=job.error_message,
    )


# ---------------------------------------------------------------------------
# Server-side rerun
# ---------------------------------------------------------------------------


async def rerun_job(
    source_job_id: uuid.UUID,
    db: AsyncSession,
    settings: Settings,
    background_tasks: BackgroundTasks,
) -> JobResponse:
    """Create a new pending job from a prior job's stored uploads.

    Validate source-job existence, confirm all original upload files are
    present, persist a new job namespace with copied inputs, enqueue
    inference, and return the newly created full job detail payload.

    Args:
        source_job_id: UUID of the job to clone.
        db: Active async database session.
        settings: Application settings (provides ``STORAGE_ROOT``).
        background_tasks: FastAPI background task queue; used to enqueue
            the inference worker after the new job is committed.

    Returns:
        Full ``JobResponse`` for the newly created pending job.

    Raises:
        HTTPException 404: Source job does not exist.
        HTTPException 409: Source job has no image results, or one or more
            upload files are no longer present on disk.
        HTTPException 422: A source upload file cannot be decoded as a valid
            image.
        HTTPException 500: An unexpected storage error occurred while copying
            files into the new job namespace.
    """
    # ==============================================================================
    # Load and validate the source job.
    # ==============================================================================
    source_result = await db.execute(select(Job).where(Job.id == source_job_id))
    source_job = source_result.scalar_one_or_none()
    if source_job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job {source_job_id} not found.",
        )

    # The Job model uses lazy="selectin" so image_results are already populated
    # after the select above.
    if not source_job.image_results:
        raise HTTPException(
            status_code=409,
            detail=f"Job {source_job_id} has no image results and cannot be rerun.",
        )

    # ==============================================================================
    # Verify all source upload files are still present.
    #
    # We fail fast here, before creating any new rows, so we never leave a new
    # pending job in the database without the files required to run it.
    # ==============================================================================
    for ir in source_job.image_results:
        source_path = Path(ir.upload_path)
        if not source_path.is_file():
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Source upload file for image {ir.original_filename!r} is no "
                    "longer available on disk. The job cannot be rerun."
                ),
            )

    # ==============================================================================
    # Create the new pending job row.
    # ==============================================================================
    new_job_id = uuid.uuid4()
    new_job = Job(
        id=new_job_id,
        status=JobStatus.pending,
        pipeline_type=source_job.pipeline_type,
        model_arch=source_job.model_arch,
    )
    db.add(new_job)

    # ==============================================================================
    # Copy source uploads into the new job storage namespace.
    #
    # Each file is read from the original upload path, written to a new
    # job-scoped directory via the same helpers as a fresh upload, and decoded
    # to regenerate a display copy.  This mirrors the create_job route path so
    # both paths produce identical storage layouts and lifecycle semantics.
    #
    # ``_written_files`` tracks every path successfully written to disk so that
    # on any failure mid-loop we can remove already-written files before
    # propagating the error.  Without cleanup those files would be orphaned:
    # the new job row is never committed, but the on-disk files have no owner
    # and will never be removed by the normal job-delete path.
    # ==============================================================================
    _written_files: list[Path] = []

    def _cleanup_written_files() -> None:
        """Best-effort removal of files written so far in this rerun attempt."""
        import logging as _logging

        _log = _logging.getLogger(__name__)
        for _path in _written_files:
            try:
                _path.unlink(missing_ok=True)
            except OSError:
                _log.warning("Could not remove orphaned file during rerun cleanup: %s", _path)

    try:
        for ir in source_job.image_results:
            source_path = Path(ir.upload_path)
            content = source_path.read_bytes()
            new_result_id = uuid.uuid4()

            # Write raw bytes into the new job upload directory.
            try:
                new_upload_path = save_upload(
                    content=content,
                    filename=ir.original_filename,
                    job_id=new_job_id,
                    settings=settings,
                )
                _written_files.append(new_upload_path)
            except (ValueError, StorageError) as exc:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to copy uploaded files for rerun.",
                ) from exc

            # Decode the source image to regenerate a fresh display copy.
            nparr = np.frombuffer(content, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Source image {ir.original_filename!r} could not be decoded. "
                        "The job cannot be rerun."
                    ),
                )

            img_float = img.astype(np.float32) / 255.0
            try:
                new_display_path = save_display_copy(
                    img=img_float,
                    image_result_id=new_result_id,
                    settings=settings,
                )
                _written_files.append(new_display_path)
            except StorageError as exc:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to create display copy for rerun.",
                ) from exc

            h, w = img.shape[:2]
            new_image_result = ImageResult(
                id=new_result_id,
                job_id=new_job_id,
                original_filename=ir.original_filename,
                upload_path=str(new_upload_path),
                display_path=str(new_display_path),
                original_size={"width": w, "height": h},
            )
            db.add(new_image_result)

    except Exception:
        # Clean up any files that were already written before the failure so
        # they are not left as orphans on disk.
        _cleanup_written_files()
        raise

    # ==============================================================================
    # Commit and enqueue inference.
    #
    # We commit before enqueueing so the new job and image_result rows are
    # visible in the database when the background task opens its own session —
    # the same ordering required by create_job.
    # ==============================================================================
    await db.commit()
    await db.refresh(new_job)

    # Late import to avoid a circular dependency: worker.py imports
    # touch_job_activity from this module, so we must not import worker.py at
    # module level here.
    from app.inference.worker import run_inference  # noqa: PLC0415

    background_tasks.add_task(run_inference, new_job_id, get_session_factory())

    return JobResponse.model_validate(new_job)
