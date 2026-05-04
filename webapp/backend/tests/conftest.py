from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer

# ---------------------------------------------------------------------------
# Add the monorepo root to sys.path so that ``src`` (which contains the
# ML model definitions) is importable when running tests locally, mirroring
# the Docker build layout where src/ is copied alongside app/.
# ---------------------------------------------------------------------------
BACKEND_ROOT = Path(__file__).resolve().parents[1]
MONOREPO_ROOT = BACKEND_ROOT.parents[1]
if str(MONOREPO_ROOT) not in sys.path:
    sys.path.insert(0, str(MONOREPO_ROOT))

from app.core.config import get_settings
from app.core.security import hash_password
from app.main import create_app
from app.models.user import User

# Plain-text passwords used when provisioning test fixtures.  Stored as
# constants so test_auth.py can reference them without hard-coding.
_TEST_USER_PASSWORD = "Password1!"
_TEST_ADMIN_PASSWORD = "AdminPass1!"

_TRUNCATE_ALL_TABLES = (
    "TRUNCATE TABLE users, oauth_accounts, image_results, jobs RESTART IDENTITY CASCADE"
)


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
async def _app(
    database_url: str,
    reset_database: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[FastAPI]:
    """Create and start the FastAPI application with test-scoped settings.

    Splitting the application out of the ``client`` fixture lets
    ``user_override`` and ``admin_override`` apply dependency overrides to
    the same ``FastAPI`` instance that ``client`` uses.
    """
    storage_root = tmp_path / "storage"
    model_root = tmp_path / "models"
    storage_root.mkdir(parents=True, exist_ok=True)
    model_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("STORAGE_ROOT", str(storage_root))
    monkeypatch.setenv("MODEL_ROOT", str(model_root))
    # A deterministic secret is sufficient for tests — it is never used
    # outside the test process and does not need to be cryptographically
    # strong in this context.
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-for-integration-tests-only")

    get_settings.cache_clear()
    app = create_app()

    async with app.router.lifespan_context(app):
        yield app

    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Unauthenticated HTTP test client backed by the test application.

    Routes that require authentication will return 401 unless a
    ``user_override`` or ``admin_override`` fixture is also active.
    """
    transport = ASGITransport(app=_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Auth fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_user(database_url: str, reset_database: None) -> AsyncIterator[User]:
    """Create a regular (non-admin) test user directly in the test database.

    The user is committed before the fixture yields so it is visible to the
    application's sessions during the test.  Password is ``_TEST_USER_PASSWORD``
    so ``test_auth.py`` can test the login flow end-to-end.
    """
    engine = create_async_engine(database_url)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        user = User(
            username="testuser",
            password_hash=hash_password(_TEST_USER_PASSWORD),
            role="user",
            must_change_pw=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        yield user
    await engine.dispose()


@pytest_asyncio.fixture
async def test_admin(database_url: str, reset_database: None) -> AsyncIterator[User]:
    """Create an admin test user directly in the test database.

    Password is ``_TEST_ADMIN_PASSWORD`` so ``test_auth.py`` can test admin
    login and admin-endpoint access.
    """
    engine = create_async_engine(database_url)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        user = User(
            username="testadmin",
            password_hash=hash_password(_TEST_ADMIN_PASSWORD),
            role="admin",
            must_change_pw=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        yield user
    await engine.dispose()


@pytest_asyncio.fixture
async def user_override(_app: FastAPI, test_user: User) -> AsyncIterator[None]:
    """Override ``get_current_user`` to return ``test_user`` for all requests.

    Apply this fixture to any test that calls a route requiring authentication
    but does not need to exercise the JWT/cookie machinery itself.  The
    override is removed after the test to leave the app clean for the next
    fixture cycle.
    """
    from app.core.auth import get_current_user

    _app.dependency_overrides[get_current_user] = lambda: test_user
    yield
    _app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def no_google_settings(_app: FastAPI) -> AsyncIterator[None]:
    """Override ``get_settings`` to return settings with Google OAuth disabled.

    Applies to tests that exercise the "Google OAuth not configured" code paths.
    The backend's ``.env`` file may contain real Google credentials, so this
    fixture injects a settings copy with all Google-related fields cleared to
    ``None``, ensuring the ``if not settings.GOOGLE_CLIENT_ID`` guard fires
    regardless of the local environment.
    """
    from app.core.config import get_settings

    real_settings = get_settings()
    no_google = real_settings.model_copy(
        update={
            "GOOGLE_CLIENT_ID": None,
            "GOOGLE_CLIENT_SECRET": None,
            "GOOGLE_REDIRECT_URI": None,
            "GOOGLE_LINK_REDIRECT_URI": None,
        }
    )
    _app.dependency_overrides[get_settings] = lambda: no_google
    yield
    _app.dependency_overrides.pop(get_settings, None)


@pytest_asyncio.fixture
async def admin_override(_app: FastAPI, test_admin: User) -> AsyncIterator[None]:
    """Override ``get_current_user`` to return ``test_admin`` for all requests.

    Apply this fixture to tests that call admin-only endpoints (``/api/admin/*``)
    or any route where admin privileges are required.
    """
    from app.core.auth import get_current_user

    _app.dependency_overrides[get_current_user] = lambda: test_admin
    yield
    _app.dependency_overrides.pop(get_current_user, None)