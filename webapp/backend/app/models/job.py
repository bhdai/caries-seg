"""SQLAlchemy ORM model for the ``jobs`` table.

Maps to the schema created by alembic migration 001.  The enum types
(``jobstatus``, ``pipelinetype``, ``modelarch``) are pre-existing
PostgreSQL native types; ``create_type=False`` tells SQLAlchemy not to
attempt to create or drop them.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class JobStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class PipelineType(str, enum.Enum):
    single_stage = "single_stage"
    two_stage = "two_stage"


class ModelArch(str, enum.Enum):
    unet = "unet"
    double_unet = "double_unet"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        # Default generated on the Python side so callers can reference
        # job.id before the INSERT is flushed.
        default=uuid.uuid4,
    )
    status: Mapped[str] = mapped_column(
        # create_type=False: the enum type already exists from migration 001.
        Enum(
            "pending", "processing", "completed", "failed",
            name="jobstatus",
            create_type=False,
        ),
        nullable=False,
        server_default="pending",
        default=JobStatus.pending,
    )
    pipeline_type: Mapped[str] = mapped_column(
        Enum(
            "single_stage", "two_stage",
            name="pipelinetype",
            create_type=False,
        ),
        nullable=False,
    )
    model_arch: Mapped[str] = mapped_column(
        Enum(
            "unet", "double_unet",
            name="modelarch",
            create_type=False,
        ),
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Nullable FK to the user who submitted the job.  SET NULL on delete so
    # that removing a user orphans their jobs (keeps diagnostic data intact)
    # rather than cascading a destructive delete — per decision D4.
    # Pre-existing rows (created before auth was added) have owner_id=NULL
    # and are visible to admins only.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        # Python-side onupdate so every flush that touches this row
        # automatically refreshes the timestamp.
        onupdate=lambda: datetime.now(tz=timezone.utc),
        nullable=False,
    )

    # Cascade-delete image_results when the job is deleted.
    image_results: Mapped[list["ImageResult"]] = relationship(  # noqa: F821
        "ImageResult",
        back_populates="job",
        cascade="all, delete-orphan",
        # selectin loading avoids an N+1 query when returning a job with
        # its results in a single endpoint response.
        lazy="selectin",
    )

    # Many jobs → one user owner (nullable; NULL means the job is orphaned).
    owner: Mapped["User | None"] = relationship(  # noqa: F821
        "User",
        back_populates="jobs",
        foreign_keys=[owner_id],
        lazy="select",
    )
