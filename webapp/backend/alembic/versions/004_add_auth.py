"""Add authentication tables: users, oauth_accounts, and jobs.owner_id.

Revision ID: 004
Revises: 003
Create Date: 2026-04-30

Changes
-------
users
  New table with id, username, password_hash, role (userrole enum),
  must_change_pw, created_at, updated_at.

oauth_accounts
  New table linking users to OAuth provider identities.
  Unique constraint on (provider, provider_account_id).

jobs
  New nullable owner_id column — FK to users.id with ON DELETE SET NULL.
  Pre-existing rows are implicitly owner_id = NULL (admin-visible only).
  Indexed for efficient per-user job list queries.

Downgrade
---------
Removes owner_id from jobs, drops oauth_accounts, drops users, drops the
userrole enum type.  Irreversible in the sense that user account data is
destroyed; downgrade is only appropriate in development or rollback
scenarios.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Create the userrole enum type.
    #
    # Using ENUM.create() rather than raw SQL so alembic tracks the type
    # and the checkfirst guard makes it idempotent in edge-case reruns.
    # ------------------------------------------------------------------
    userrole = postgresql.ENUM("user", "admin", name="userrole", create_type=False)
    userrole.create(op.get_bind(), checkfirst=True)

    # ------------------------------------------------------------------
    # users
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("username", sa.String(150), nullable=False),
        # Nullable to support OAuth-only accounts with no local password.
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column(
            "role",
            userrole,
            nullable=False,
            server_default="user",
        ),
        # Frontend forces a password change on the first login when True.
        sa.Column(
            "must_change_pw",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )

    # ------------------------------------------------------------------
    # oauth_accounts
    # ------------------------------------------------------------------
    op.create_table(
        "oauth_accounts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_account_id", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "provider_account_id",
            name="uq_oauth_provider_account",
        ),
    )

    # ------------------------------------------------------------------
    # jobs.owner_id — nullable FK, SET NULL on user delete
    # ------------------------------------------------------------------
    op.add_column(
        "jobs",
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_jobs_owner_id_users",
        "jobs",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_jobs_owner_id", "jobs", ["owner_id"])


def downgrade() -> None:
    # Remove in reverse order to avoid FK violations.
    op.drop_index("ix_jobs_owner_id", table_name="jobs")
    op.drop_constraint("fk_jobs_owner_id_users", "jobs", type_="foreignkey")
    op.drop_column("jobs", "owner_id")

    op.drop_table("oauth_accounts")
    op.drop_table("users")

    # Drop the enum type only after the tables that reference it are gone.
    userrole = postgresql.ENUM("user", "admin", name="userrole", create_type=False)
    userrole.drop(op.get_bind(), checkfirst=True)
