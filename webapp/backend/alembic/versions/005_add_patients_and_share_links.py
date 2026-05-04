"""Add patients and share_links tables; add jobs.patient_id FK.

Revision ID: 005
Revises: 004
Create Date: 2026-05-04

Changes
-------
patients
  New table for clinic patient records with soft-delete support.
  Columns: id, full_name, date_of_birth, phone, notes, deleted_at,
  created_at, updated_at.

share_links
  New table for cryptographically-random share tokens that grant
  unauthenticated patients read-only access to a single job's results.
  Columns: id, job_id (FK → jobs CASCADE), token (UNIQUE VARCHAR 64),
  expires_at, created_by_id (FK → users SET NULL), created_at.
  Indexed on token for fast single-row lookup by public endpoints.

jobs
  New nullable patient_id column — FK to patients.id with ON DELETE SET NULL.
  Pre-existing rows receive patient_id = NULL implicitly.
  Indexed for efficient per-patient job list queries.

Downgrade
---------
Removes patient_id from jobs, drops share_links, drops patients.
Patient and share_link data is destroyed; downgrade is only appropriate
in development or rollback scenarios.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # patients table
    # ------------------------------------------------------------------
    op.create_table(
        "patients",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("full_name", sa.String(255), nullable=False),
        # Optional demographic fields captured at intake.
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        # Soft-delete marker; NULL = active.
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
    )

    # ------------------------------------------------------------------
    # share_links table
    #
    # Created in the same migration as patients so both entities arrive
    # atomically.  share_links routes/services are wired in Phase 2; the
    # table is ready here so Phase 1 tests already run against the
    # correct schema.
    # ------------------------------------------------------------------
    op.create_table(
        "share_links",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        # CASCADE: removing a job removes all associated share tokens so
        # orphaned tokens can never resolve.
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        # VARCHAR(64) is generous for token_urlsafe(32) output (43 chars),
        # leaving room if the token strategy changes without a re-migration.
        sa.Column("token", sa.String(64), nullable=False),
        # NULL means the link never expires.
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        # SET NULL: removing a user doesn't revoke their issued share links.
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            ondelete="CASCADE",
            name="fk_share_links_job_id_jobs",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_share_links_created_by_id_users",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_share_links_token"),
    )

    # Index on token for O(log n) public-endpoint lookup.
    op.create_index("ix_share_links_token", "share_links", ["token"])

    # ------------------------------------------------------------------
    # jobs.patient_id — nullable FK, SET NULL on patient delete
    # ------------------------------------------------------------------
    op.add_column(
        "jobs",
        sa.Column(
            "patient_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_jobs_patient_id_patients",
        "jobs",
        "patients",
        ["patient_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_jobs_patient_id", "jobs", ["patient_id"])


def downgrade() -> None:
    # Remove in reverse creation order to avoid FK violations.
    op.drop_index("ix_jobs_patient_id", table_name="jobs")
    op.drop_constraint("fk_jobs_patient_id_patients", "jobs", type_="foreignkey")
    op.drop_column("jobs", "patient_id")

    op.drop_index("ix_share_links_token", table_name="share_links")
    op.drop_table("share_links")

    op.drop_table("patients")
