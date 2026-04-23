"""Remove attention_unet from the modelarch PostgreSQL enum type.

Revision ID: 002
Revises: 001
Create Date: 2026-04-23

Rationale
---------
No AttentionUNet checkpoint exists for the webapp (neither single-stage
nor two-stage). Keeping the value in the enum allowed jobs to be accepted
and then fail silently at inference time. Removing it causes invalid
submissions to be rejected immediately with HTTP 422 by the Pydantic
form-field validator.

PostgreSQL does not support ``ALTER TYPE ... DROP VALUE``, so we use the
rename-and-recreate pattern:

  1. Rename the old type to a temporary name.
  2. Create a new type with only the supported values.
  3. Alter the column to cast to the new type.
  4. Drop the old type.

Downgrade reverses the steps, adding ``attention_unet`` back.
"""

from __future__ import annotations

from alembic import op


revision: str = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1 — rename the current enum so we can create the new one with the
    # same name once the column is migrated.
    op.execute("ALTER TYPE modelarch RENAME TO modelarch_old")

    # Step 2 — create the trimmed enum (no attention_unet).
    op.execute("CREATE TYPE modelarch AS ENUM ('unet', 'double_unet')")

    # Step 3 — migrate the column.  Any row containing 'attention_unet'
    # would fail the cast; there should be none in a fresh deploy, but add
    # a safety delete so the migration does not abort on stale data.
    op.execute(
        "DELETE FROM jobs WHERE model_arch::text = 'attention_unet'"
    )
    op.execute(
        "ALTER TABLE jobs "
        "ALTER COLUMN model_arch TYPE modelarch "
        "USING model_arch::text::modelarch"
    )

    # Step 4 — drop the old type now that nothing references it.
    op.execute("DROP TYPE modelarch_old")


def downgrade() -> None:
    # Reverse: add attention_unet back.
    op.execute("ALTER TYPE modelarch RENAME TO modelarch_old")
    op.execute(
        "CREATE TYPE modelarch AS ENUM ('unet', 'double_unet', 'attention_unet')"
    )
    op.execute(
        "ALTER TABLE jobs "
        "ALTER COLUMN model_arch TYPE modelarch "
        "USING model_arch::text::modelarch"
    )
    op.execute("DROP TYPE modelarch_old")
