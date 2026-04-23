"""SQLAlchemy async engine, session factory, and FastAPI dependency.

The engine is **not** created at module import time.  Call ``init_db(url)``
from the application lifespan (or from test setup) to initialise the
module-level singletons before any handler runs.

The ``get_db`` FastAPI dependency yields a per-request ``AsyncSession``
and auto-commits on clean exit or rolls back on exception.
"""

from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# ---------------------------------------------------------------------------
# Module-level singletons
#
# These are set by init_db() and used by get_db().  Keeping them at module
# scope means the same engine (and its connection pool) is shared across
# all requests without being re-created on every call.
# ---------------------------------------------------------------------------
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_db(database_url: str) -> None:
    """Initialise the async engine and session factory.

    Must be called once before any handler or test that uses ``get_db``.
    Calling a second time replaces the existing engine, which is useful in
    tests that need a fresh connection pool pointed at a different database.

    Args:
        database_url: An ``asyncpg``-compatible URL, e.g.
            ``postgresql+asyncpg://user:pass@host/db``.
    """
    global _engine, _session_factory
    if _engine is not None:
        _engine.sync_engine.dispose()

    _engine = create_async_engine(database_url, echo=False, pool_pre_ping=True)
    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the module-level session factory.

    Raises:
        AssertionError: If ``init_db()`` has not been called yet.
    """
    assert _session_factory is not None, (
        "init_db() must be called before get_session_factory()"
    )
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield a per-request ``AsyncSession``.

    The session is committed on success or rolled back on exception,
    then closed in either case.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
