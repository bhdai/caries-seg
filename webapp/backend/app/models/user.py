"""SQLAlchemy ORM model for the ``users`` table.

Maps to the schema created by alembic migration 002.  The ``userrole``
PostgreSQL enum type is created by that migration; ``create_type=False``
tells SQLAlchemy not to attempt to create it on its own.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserRole(str, enum.Enum):
    user = "user"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        # Python-side default so callers can reference user.id before the
        # INSERT is flushed.  The migration also sets gen_random_uuid() as
        # the server_default for rows inserted via raw SQL.
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    username: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        nullable=False,
    )
    # Nullable to support OAuth-only accounts that have no local password.
    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    role: Mapped[str] = mapped_column(
        # create_type=False: migration 002 creates the userrole enum type.
        Enum(
            "user", "admin",
            name="userrole",
            create_type=False,
        ),
        nullable=False,
        server_default="user",
        default=UserRole.user,
    )
    # When True the frontend forces the user to change their password before
    # proceeding.  Admin-provisioned accounts always start with this set.
    must_change_pw: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
        default=True,
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

    # One user → many OAuth provider links.  Deleting the user cascades to
    # their OAuth accounts so provider records don't become orphans.
    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(  # noqa: F821
        "OAuthAccount",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # One user → many jobs.  back_populates wired on Job.owner (added in 1.3).
    # No cascade here — deleting a user orphans their jobs (owner_id → NULL)
    # rather than deleting diagnostic data, per decision D4.
    jobs: Mapped[list["Job"]] = relationship(  # noqa: F821
        "Job",
        back_populates="owner",
        foreign_keys="Job.owner_id",
        lazy="select",
    )
