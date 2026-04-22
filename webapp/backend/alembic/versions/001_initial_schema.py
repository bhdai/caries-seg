"""Initial schema — jobs and image_results tables.

Revision ID: 001
Revises: (none)
Create Date: 2026-04-22

Creates:
  - PostgreSQL enum types: jobstatus, pipelinetype, modelarch
  - Table: jobs
  - Table: image_results  (FK → jobs.id CASCADE DELETE)
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Enum types
    #
    # Creating them explicitly (rather than via SQLAlchemy Enum's
    # create_constraint=True) gives us control over when they are
    # dropped and avoids conflicts if an enum is shared across tables.
    # ------------------------------------------------------------------
    job_status = postgresql.ENUM(
        "pending", "processing", "completed", "failed",
        name="jobstatus",
    )
    pipeline_type = postgresql.ENUM(
        "single_stage", "two_stage",
        name="pipelinetype",
    )
    model_arch = postgresql.ENUM(
        "unet", "double_unet", "attention_unet",
        name="modelarch",
    )
    job_status.create(op.get_bind(), checkfirst=True)
    pipeline_type.create(op.get_bind(), checkfirst=True)
    model_arch.create(op.get_bind(), checkfirst=True)

    # ------------------------------------------------------------------
    # jobs table
    # ------------------------------------------------------------------
    op.create_table(
        "jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("pending", "processing", "completed", "failed", name="jobstatus", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "pipeline_type",
            sa.Enum("single_stage", "two_stage", name="pipelinetype", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "model_arch",
            sa.Enum("unet", "double_unet", "attention_unet", name="modelarch", create_type=False),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
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

    # Index to support polling queries filtered by status.
    op.create_index("ix_jobs_status", "jobs", ["status"])

    # ------------------------------------------------------------------
    # image_results table
    # ------------------------------------------------------------------
    op.create_table(
        "image_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        # Original filename as submitted by the browser.
        sa.Column("original_filename", sa.String(255), nullable=False),
        # Absolute path inside the storage volume where the raw upload lives.
        sa.Column("upload_path", sa.String(1024), nullable=False),
        # Resized display copy for fast browser rendering (null until produced).
        sa.Column("display_path", sa.String(1024), nullable=True),
        # Binary mask PNG path (null until inference completes).
        sa.Column("mask_path", sa.String(1024), nullable=True),
        # YOLO bounding boxes; null for single-stage jobs.
        sa.Column("bounding_boxes", postgresql.JSONB(), nullable=True),
        # Wall-clock inference duration in milliseconds (null until complete).
        sa.Column("inference_time_ms", sa.Integer(), nullable=True),
        # Original image dimensions, e.g. {"width": 2048, "height": 1024}.
        sa.Column("original_size", postgresql.JSONB(), nullable=False),
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
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Index to support fetching all results for a given job in one query.
    op.create_index("ix_image_results_job_id", "image_results", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_image_results_job_id", table_name="image_results")
    op.drop_table("image_results")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_table("jobs")

    # Drop enum types after their dependent tables are gone.
    op.execute("DROP TYPE IF EXISTS modelarch")
    op.execute("DROP TYPE IF EXISTS pipelinetype")
    op.execute("DROP TYPE IF EXISTS jobstatus")
