"""Alembic migration environment.

Configured for async SQLAlchemy (asyncpg driver).  Alembic itself is
synchronous, so we bridge to the async engine with
``connection.run_sync(do_run_migrations)`` following the pattern described
in the SQLAlchemy async migration docs.

The database URL is read exclusively from the ``DATABASE_URL`` environment
variable so that credentials are never stored in this file or in alembic.ini.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context

# ---------------------------------------------------------------------------
# Alembic config object — gives access to values in alembic.ini.
# ---------------------------------------------------------------------------
config = context.config

# Activate logging from alembic.ini if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# ORM metadata for autogenerate support.
#
# In Phase 2 this will be replaced by the imported Base.metadata from the
# ORM models package.  We set it to None for now so that `alembic revision
# --autogenerate` produces an empty (but valid) migration.
# ---------------------------------------------------------------------------
target_metadata = None


# ---------------------------------------------------------------------------
# Helper: inject DATABASE_URL from the environment into the Alembic config.
# ---------------------------------------------------------------------------
def _get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    assert url, (
        "DATABASE_URL environment variable must be set before running Alembic"
    )
    return url


# ---------------------------------------------------------------------------
# Offline mode — generate SQL script without a live DB connection.
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode — connect to the database and apply migrations.
# ---------------------------------------------------------------------------
def do_run_migrations(connection) -> None:  # type: ignore[type-arg]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    url = _get_database_url()
    connectable = create_async_engine(url, echo=False)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entry point selected by Alembic based on the --sql flag.
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
