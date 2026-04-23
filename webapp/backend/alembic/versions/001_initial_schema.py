"""Initial schema for jobs and image_results.

Revision ID: 001
Revises: (none)
Create Date: 2026-04-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The migration uses gen_random_uuid() server defaults, so pgcrypto
    # must exist before either table is created.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    job_status = postgresql.ENUM(
        "pending",
        "processing",
        "completed",
        "failed",
        name="jobstatus",
        create_type=False,
    )
    pipeline_type = postgresql.ENUM(
        "single_stage",
        "two_stage",
        name="pipelinetype",
        create_type=False,
    )
    model_arch = postgresql.ENUM(
        "unet",
        "double_unet",
        "attention_unet",
        name="modelarch",
        create_type=False,
    )

    job_status.create(op.get_bind(), checkfirst=True)
    pipeline_type.create(op.get_bind(), checkfirst=True)
    model_arch.create(op.get_bind(), checkfirst=True)

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
            job_status,
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "pipeline_type",
            pipeline_type,
            nullable=False,
        ),
        sa.Column(
            "model_arch",
            model_arch,
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
    op.create_index("ix_jobs_status", "jobs", ["status"])

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
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("upload_path", sa.String(1024), nullable=False),
        sa.Column("display_path", sa.String(1024), nullable=True),
        sa.Column("mask_path", sa.String(1024), nullable=True),
        sa.Column("bounding_boxes", postgresql.JSONB(), nullable=True),
        sa.Column("inference_time_ms", sa.Integer(), nullable=True),
        sa.Column("original_size", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_image_results_job_id", "image_results", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_image_results_job_id", table_name="image_results")
    op.drop_table("image_results")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_table("jobs")
    op.execute("DROP TYPE IF EXISTS modelarch")
    op.execute("DROP TYPE IF EXISTS pipelinetype")
    op.execute("DROP TYPE IF EXISTS jobstatus")
