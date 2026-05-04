"""SQLAlchemy ORM model for the ``patients`` table.

Patients are clinic-level records that can be linked to inference jobs so that
result history is associated with a specific person.  The table supports
soft-deletion: setting ``deleted_at`` to the current timestamp hides a patient
from all list and search queries without destroying their associated job history.

Patients are created by clinic staff; they are distinct from the ``users``
table which represents authenticated application users (doctors/admins).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        # Python-side default so callers can reference patient.id before the
        # INSERT is flushed.  The migration also sets gen_random_uuid() as
        # the server_default for rows inserted via raw SQL.
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )

    # Full name as displayed in the UI.  No unique constraint — different
    # patients legitimately share names (e.g. "Nguyen Van A" is common).
    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Optional demographic fields captured at intake.
    date_of_birth: Mapped[date | None] = mapped_column(
        # Store as a plain DATE column; Python renders it as datetime.date.
        nullable=True,
    )
    phone: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Soft-delete marker.  NULL means the patient is active and visible in all
    # list/search results.  A non-null timestamp means the patient has been
    # archived and is excluded from queries.  Linked jobs retain the patient_id
    # FK for historical audit; they are not affected by the soft-delete.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(tz=timezone.utc),
        nullable=False,
    )

    # One patient → many jobs.  The back-populate is wired on ``Job.patient``.
    # lazy="select" is intentional: patient detail pages load linked jobs
    # explicitly via a service-layer query rather than traversing this
    # relationship, so eager loading here would only waste joins.
    jobs: Mapped[list["Job"]] = relationship(  # noqa: F821
        "Job",
        back_populates="patient",
        lazy="select",
    )
