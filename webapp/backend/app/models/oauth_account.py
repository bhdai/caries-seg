"""SQLAlchemy ORM model for the ``oauth_accounts`` table.

Each row links a User to a single OAuth provider identity (e.g. Google).
The design supports multiple providers per user and prevents two accounts
from claiming the same provider identity via the unique constraint on
(provider, provider_account_id).

Maps to the schema created by alembic migration 002.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"
    __table_args__ = (
        # Prevent two users from claiming the same provider identity.
        UniqueConstraint(
            "provider",
            "provider_account_id",
            name="uq_oauth_provider_account",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Short provider name, e.g. "google".  VARCHAR(50) leaves room for future
    # providers (github, microsoft, …) without needing a migration.
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    # The ``sub`` claim from an OIDC id_token, or the equivalent unique
    # identifier from the provider's user-info endpoint.
    provider_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Many OAuth accounts → one user.
    user: Mapped["User"] = relationship(  # noqa: F821
        "User",
        back_populates="oauth_accounts",
    )
