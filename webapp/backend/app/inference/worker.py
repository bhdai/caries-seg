"""Inference background worker.

``run_inference`` is the function passed to FastAPI ``BackgroundTasks``.
It opens its own database session (independent of the HTTP request session
that created the job), runs the appropriate pipeline for each uploaded
image, and persists the results.

PyTorch inference is blocking (the GIL is held while GPU kernels execute
on CPU-synchronous paths).  Each synchronous pipeline call is therefore
wrapped in ``asyncio.to_thread`` so the event loop remains responsive to
other requests while a job is in flight.

Error handling:
    Any exception raised during inference (model error, file I/O, etc.)
    is caught, logged with a full traceback, and written to
    ``job.error_message`` before the job is marked ``"failed"``.  The
    exception is not re-raised because BackgroundTasks cannot surface it
    to the caller anyway.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.inference import registry as _registry_module
from app.inference.single_stage import run_single_stage
from app.inference.two_stage import run_two_stage
from app.models.image_result import ImageResult
from app.models.job import Job, JobStatus

logger = logging.getLogger(__name__)


async def run_inference(
    job_id: uuid.UUID,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Background task: load job, run inference on all images, persist results.

    Opens its own DB session independent of the HTTP request session.
    Sets ``job.status = "processing"`` at the start and ``"completed"`` or
    ``"failed"`` at the end.  On any exception, writes the formatted
    traceback to ``job.error_message`` before closing the session.

    Args:
        job_id: UUID of the job to process.
        session_factory: SQLAlchemy async session factory from
            ``database.get_session_factory()``.
    """
    from app.core.config import get_settings

    settings = get_settings()

    async with session_factory() as session:
        try:
            # ------------------------------------------------------------------
            # Mark the job as processing so polling clients see activity.
            # ------------------------------------------------------------------
            job = await session.get(Job, job_id)
            if job is None:
                logger.error("run_inference: job %s not found in database", job_id)
                return

            job.status = JobStatus.processing
            await session.commit()

            # Load all image results for this job.  We access them after the
            # commit so SQLAlchemy does not hold them as pending-flush objects
            # across the long-running inference calls.
            result = await session.execute(
                select(ImageResult).where(ImageResult.job_id == job_id)
            )
            image_results = list(result.scalars().all())

            # ------------------------------------------------------------------
            # Run inference for each uploaded image sequentially.
            #
            # Sequential processing avoids out-of-memory errors on GPU when
            # multiple large panoramics are in one job.
            # ------------------------------------------------------------------
            registry = _registry_module.registry
            assert registry is not None, "ModelRegistry must be initialised before inference"

            for ir in image_results:
                if job.pipeline_type == "single_stage":
                    model = registry.get(job.pipeline_type, job.model_arch)
                    output = await asyncio.to_thread(
                        run_single_stage, ir, model, settings
                    )
                else:
                    # two_stage
                    yolo = registry.get_yolo()
                    seg_model = registry.get(job.pipeline_type, job.model_arch)
                    output = await asyncio.to_thread(
                        run_two_stage, ir, yolo, seg_model, settings
                    )

                # Persist inference outputs for this image result.
                ir.mask_path = str(output.mask_path)
                ir.display_path = str(output.display_path)
                ir.inference_time_ms = output.inference_time_ms
                ir.bounding_boxes = (
                    [
                        {
                            "x1": b.x1,
                            "y1": b.y1,
                            "x2": b.x2,
                            "y2": b.y2,
                            "confidence": b.confidence,
                        }
                        for b in output.bounding_boxes
                    ]
                    if output.bounding_boxes is not None
                    else None
                )
                await session.commit()

            # ------------------------------------------------------------------
            # All images processed successfully — mark the job completed.
            # ------------------------------------------------------------------
            job.status = JobStatus.completed
            await session.commit()
            logger.info("Job %s completed successfully", job_id)

        except Exception:
            # ------------------------------------------------------------------
            # On any failure: roll back any partial write, then record the
            # error so the frontend can display a meaningful message.
            # ------------------------------------------------------------------
            await session.rollback()
            error_summary = traceback.format_exc()
            logger.exception("Inference failed for job %s", job_id)

            # Open a fresh transaction to persist the failure status.
            try:
                job = await session.get(Job, job_id)
                if job is not None:
                    job.status = JobStatus.failed
                    job.error_message = error_summary
                    await session.commit()
            except Exception:
                logger.exception(
                    "Failed to persist error status for job %s", job_id
                )
