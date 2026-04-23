from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from app.core.config import get_settings
from app.main import create_app


BACKEND_ROOT = Path(__file__).resolve().parents[1]
_TRUNCATE_ALL_TABLES = "TRUNCATE TABLE image_results, jobs RESTART IDENTITY CASCADE"


def _to_asyncpg_url(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg2://"):
        return database_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


def _run_migrations(database_url: str) -> None:
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(alembic_config, "head")
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    with PostgresContainer("postgres:16-alpine") as postgres:
        database_url = _to_asyncpg_url(postgres.get_connection_url())
        _run_migrations(database_url)
        yield database_url


@pytest_asyncio.fixture
async def reset_database(database_url: str) -> AsyncIterator[None]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    async with engine.begin() as connection:
        await connection.execute(text(_TRUNCATE_ALL_TABLES))

    try:
        yield
    finally:
        async with engine.begin() as connection:
            await connection.execute(text(_TRUNCATE_ALL_TABLES))
        await engine.dispose()


@pytest_asyncio.fixture
async def client(
    database_url: str,
    reset_database: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    storage_root = tmp_path / "storage"
    model_root = tmp_path / "models"
    storage_root.mkdir(parents=True, exist_ok=True)
    model_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("STORAGE_ROOT", str(storage_root))
    monkeypatch.setenv("MODEL_ROOT", str(model_root))

    get_settings.cache_clear()
    app = create_app()

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as test_client:
            yield test_client

    get_settings.cache_clear()