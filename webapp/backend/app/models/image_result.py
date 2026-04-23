"""SQLAlchemy ORM model for the ``image_results`` table.

Each row represents one uploaded image within a job.  Paths to the
display copy and mask are populated by the inference worker (Phase 3);
they are ``None`` until inference completes.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ImageResult(Base):
    __tablename__ = "image_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # Absolute path inside the storage volume where the raw upload lives.
    upload_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    # Resized display copy for fast browser rendering (null until produced).
    display_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Binary mask PNG path (null until inference completes).
    mask_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # YOLO bounding boxes; null for single-stage jobs or when not yet inferred.
    bounding_boxes: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    # Wall-clock inference duration in milliseconds (null until complete).
    inference_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Original image dimensions, e.g. {"width": 2048, "height": 1024}.
    original_size: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    job: Mapped["Job"] = relationship(  # noqa: F821
        "Job",
        back_populates="image_results",
    )
