from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import pool

from alembic import context

# Alembic Config object — access to values in alembic.ini.
config = context.config

# Set up logging from alembic.ini if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# ORM metadata for autogenerate support.
#
# Importing app.models registers all model classes with Base.metadata so
# that autogenerate can detect table differences.
# ---------------------------------------------------------------------------
import app.models  # noqa: F401 — side-effect import registers ORM models
from app.core.database import Base

target_metadata = Base.metadata


def _get_url() -> str:
    """Read the database URL from the environment.

    The URL is intentionally not stored in alembic.ini to keep credentials
    out of version control.
    """
    url = os.environ.get("DATABASE_URL")
    assert url, "DATABASE_URL environment variable must be set before running Alembic"
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a live connection)."""
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:  # type: ignore[type-arg]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations through a sync bridge.

    Alembic is synchronous; ``connection.run_sync`` bridges into the async
    engine following the pattern from the SQLAlchemy async migration docs.
    """
    engine = create_async_engine(_get_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
