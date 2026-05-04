"""SQLAlchemy ORM model for the ``share_links`` table.

A share link is a short-lived, cryptographically random token that gives
unauthenticated patients read-only access to one job's inference results.
The token is generated with ``secrets.token_urlsafe(32)`` (192 bits of
entropy), making brute-force enumeration computationally infeasible.

Share link creation and revocation are implemented in Phase 2.  This model
is created here (in the same migration as ``patients``) so the database schema
is established before Phase 2 routes and services are wired up.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ShareLink(Base):
    __tablename__ = "share_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # The job whose results this link exposes.  Cascade delete ensures that
    # share links are automatically removed when the linked job is deleted.
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    # The publicly-shareable token.  Unique index enforced by the migration.
    # Generated at the application layer via secrets.token_urlsafe(32).
    token: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )

    # Optional expiry.  NULL means the link never expires.
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # User who created the link.  SET NULL on delete so that removing a user
    # account doesn't cascade-delete their issued share links (which patients
    # might still be using).
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Many share links → one job.  back_populates wired on ``Job.share_links``.
    job: Mapped["Job"] = relationship(  # noqa: F821
        "Job",
        back_populates="share_links",
    )

    # Many share links → one creator (nullable).
    created_by: Mapped["User | None"] = relationship(  # noqa: F821
        "User",
        foreign_keys=[created_by_id],
        lazy="select",
    )
