"""Add targeted indexes for job history list and filename search.

Revision ID: 003
Revises: 002
Create Date: 2026-04-24

Rationale
---------
The new GET /api/jobs list endpoint applies several WHERE, ORDER BY, and
search conditions that would require full table scans without indexes.

Indexes added by this migration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
(``ix_jobs_status`` and ``ix_image_results_job_id`` were already created
by migration 001 and are intentionally not repeated here.)

jobs
  ix_jobs_updated_at    — supports the default ``last_activity_desc`` sort
  ix_jobs_created_at    — supports ``newest`` / ``oldest`` sort variants
  ix_jobs_pipeline_type — supports pipeline_type filter
  ix_jobs_model_arch    — supports model_arch filter

image_results
  ix_image_results_original_filename — filename search via ILIKE
"""

from __future__ import annotations

from alembic import op

revision: str = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --------------------------------------------------------------------------
    # jobs table
    # --------------------------------------------------------------------------

    # Default sort: most recently active jobs first.
    op.create_index("ix_jobs_updated_at", "jobs", ["updated_at"], unique=False)

    # Alternative sorts: chronological and reverse-chronological.
    op.create_index("ix_jobs_created_at", "jobs", ["created_at"], unique=False)

    # Equality filters applied by the list endpoint.
    op.create_index("ix_jobs_pipeline_type", "jobs", ["pipeline_type"], unique=False)
    op.create_index("ix_jobs_model_arch", "jobs", ["model_arch"], unique=False)

    # --------------------------------------------------------------------------
    # image_results table
    # --------------------------------------------------------------------------

    # Filename search via ILIKE.  A btree index will not accelerate
    # arbitrary mid-string patterns, but it does help prefix searches and
    # equality lookups, and keeps the option open to add a trigram index
    # later without a migration rewrite.
    op.create_index(
        "ix_image_results_original_filename",
        "image_results",
        ["original_filename"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_image_results_original_filename", table_name="image_results")
    op.drop_index("ix_jobs_model_arch", table_name="jobs")
    op.drop_index("ix_jobs_pipeline_type", table_name="jobs")
    op.drop_index("ix_jobs_created_at", table_name="jobs")
    op.drop_index("ix_jobs_updated_at", table_name="jobs")
