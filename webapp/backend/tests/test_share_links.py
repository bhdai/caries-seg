"""Integration tests for share link creation, revocation, and public access.

Covers all 15 test cases described in
``_develop/plan/patient-linking/04-data-flow-and-testing.md``
under "Key Test Cases: test_share_links.py".

Fixtures used:
- ``client``           — unauthenticated HTTPX client
- ``user_override``    — makes requests act as ``test_user``
- ``admin_override``   — makes requests act as ``test_admin``
- ``test_user``        — a regular (non-admin) User ORM instance
- ``test_admin``       — an admin User ORM instance
- ``test_patient``     — a single active Patient ORM instance
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.image_result import ImageResult
from app.models.job import Job, JobStatus
from app.models.patient import Patient
from app.models.share_link import ShareLink
from app.models.user import User


# ==============================================================================
# Local fixtures
# ==============================================================================


@pytest_asyncio.fixture
async def test_job(
    database_url: str,
    reset_database: None,
    test_user: User,
) -> AsyncIterator[Job]:
    """Create a completed job owned by ``test_user`` with one image result.

    The image result has a stub ``upload_path`` and ``display_path`` so that
    the public file-serving endpoints can resolve the path in test cases that
    exercise file access.  The paths point into a temporary directory created
    by pytest's ``tmp_path`` fixture — tests that need real bytes on disk
    should create them explicitly.
    """
    engine = create_async_engine(database_url)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        job = Job(
            status=JobStatus.completed,
            pipeline_type="single_stage",
            model_arch="unet",
            owner_id=test_user.id,
        )
        session.add(job)
        await session.flush()

        image_result = ImageResult(
            job_id=job.id,
            original_filename="xray.jpg",
            upload_path=f"/storage/{job.id}/upload.jpg",
            display_path=f"/storage/{job.id}/display.png",
            original_size={"width": 1024, "height": 512},
        )
        session.add(image_result)
        await session.commit()
        await session.refresh(job)
        yield job
    await engine.dispose()


@pytest_asyncio.fixture
async def other_user(database_url: str, reset_database: None) -> AsyncIterator[User]:
    """Create a second regular user to test cross-ownership access control."""
    from app.core.security import hash_password

    engine = create_async_engine(database_url)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        user = User(
            username="otheruser",
            password_hash=hash_password("OtherPass1!"),
            role="user",
            must_change_pw=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        yield user
    await engine.dispose()


@pytest_asyncio.fixture
async def other_user_override(_app: Any, other_user: User) -> AsyncIterator[None]:
    """Override ``get_current_user`` to return ``other_user`` for all requests."""
    from app.core.auth import get_current_user

    _app.dependency_overrides[get_current_user] = lambda: other_user
    yield
    _app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def active_share_link(
    database_url: str,
    reset_database: None,
    test_user: User,
    test_job: Job,
) -> AsyncIterator[ShareLink]:
    """Create an active share link for ``test_job`` directly in the database."""
    import secrets

    engine = create_async_engine(database_url)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        link = ShareLink(
            job_id=test_job.id,
            token=secrets.token_urlsafe(32),
            expires_at=datetime.now(tz=timezone.utc) + timedelta(days=30),
            created_by_id=test_user.id,
        )
        session.add(link)
        await session.commit()
        await session.refresh(link)
        yield link
    await engine.dispose()


# ==============================================================================
# Authenticated endpoints — test cases 1–8
# ==============================================================================


@pytest.mark.asyncio
async def test_create_share_link(
    client: AsyncClient,
    user_override: None,
    test_job: Job,
) -> None:
    """1. POST /api/share-links for own job → 201 with active link payload."""
    resp = await client.post(
        "/api/share-links",
        json={"job_id": str(test_job.id), "expires_in_days": 30},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "token" in data
    assert len(data["token"]) > 0
    assert data["is_active"] is True
    assert data["job_id"] == str(test_job.id)


@pytest.mark.asyncio
async def test_create_share_link_idempotent(
    client: AsyncClient,
    user_override: None,
    test_job: Job,
) -> None:
    """2. POST twice for the same job → returns the same link both times."""
    resp1 = await client.post(
        "/api/share-links",
        json={"job_id": str(test_job.id), "expires_in_days": 30},
    )
    assert resp1.status_code == 201
    token1 = resp1.json()["token"]

    resp2 = await client.post(
        "/api/share-links",
        json={"job_id": str(test_job.id), "expires_in_days": 30},
    )
    assert resp2.status_code == 201
    token2 = resp2.json()["token"]

    # The same token is returned; no duplicate row is inserted.
    assert token1 == token2


@pytest.mark.asyncio
async def test_create_share_link_with_expiry(
    client: AsyncClient,
    user_override: None,
    test_job: Job,
) -> None:
    """3. POST with expires_in_days=7 → expires_at is approximately 7 days from now."""
    resp = await client.post(
        "/api/share-links",
        json={"job_id": str(test_job.id), "expires_in_days": 7},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["expires_at"] is not None

    expires_at = datetime.fromisoformat(data["expires_at"])
    # Allow a 10-second window for test execution latency.
    expected = datetime.now(tz=timezone.utc) + timedelta(days=7)
    assert abs((expires_at - expected).total_seconds()) < 10


@pytest.mark.asyncio
async def test_create_share_link_no_expiry(
    client: AsyncClient,
    user_override: None,
    test_job: Job,
) -> None:
    """4. POST with expires_in_days=null → expires_at is null (link never expires)."""
    resp = await client.post(
        "/api/share-links",
        json={"job_id": str(test_job.id), "expires_in_days": None},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["expires_at"] is None
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_share_link_for_others_job(
    client: AsyncClient,
    other_user_override: None,
    test_job: Job,
) -> None:
    """5. POST as user B for user A's job → 403 Forbidden."""
    resp = await client.post(
        "/api/share-links",
        json={"job_id": str(test_job.id), "expires_in_days": 30},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_share_link_admin(
    client: AsyncClient,
    admin_override: None,
    test_job: Job,
) -> None:
    """6. POST as admin for any job → 201 (admin bypasses ownership check)."""
    resp = await client.post(
        "/api/share-links",
        json={"job_id": str(test_job.id), "expires_in_days": 30},
    )
    assert resp.status_code == 201
    assert "token" in resp.json()


@pytest.mark.asyncio
async def test_revoke_share_link(
    client: AsyncClient,
    user_override: None,
    active_share_link: ShareLink,
) -> None:
    """7. DELETE /api/share-links/:id → 204, link no longer accessible publicly."""
    revoke_resp = await client.delete(f"/api/share-links/{active_share_link.id}")
    assert revoke_resp.status_code == 204

    # Verify that the public endpoint now returns 404.
    public_resp = await client.get(f"/api/shared/{active_share_link.token}")
    assert public_resp.status_code == 404


@pytest.mark.asyncio
async def test_revoke_share_link_wrong_owner(
    client: AsyncClient,
    other_user_override: None,
    active_share_link: ShareLink,
) -> None:
    """8. DELETE as user B on user A's job's link → 403 Forbidden."""
    resp = await client.delete(f"/api/share-links/{active_share_link.id}")
    assert resp.status_code == 403


# ==============================================================================
# Public endpoints — test cases 9–15
# ==============================================================================


@pytest.mark.asyncio
async def test_public_access_valid_token(
    client: AsyncClient,
    active_share_link: ShareLink,
) -> None:
    """9. GET /api/shared/:token with valid token → 200 SharedResultResponse."""
    resp = await client.get(f"/api/shared/{active_share_link.token}")
    assert resp.status_code == 200
    data = resp.json()
    # Required fields present.
    assert "scan_date" in data
    assert "image_results" in data
    assert isinstance(data["image_results"], list)
    assert len(data["image_results"]) == 1
    assert data["image_results"][0]["original_filename"] == "xray.jpg"


@pytest.mark.asyncio
async def test_public_access_expired_token(
    database_url: str,
    client: AsyncClient,
    active_share_link: ShareLink,
) -> None:
    """10. Create link with past expiry → GET returns 410 with expired flag."""
    # Manually set expires_at to the past to simulate an expired link.
    engine = create_async_engine(database_url)
    async with AsyncSession(engine) as session:
        await session.execute(
            update(ShareLink)
            .where(ShareLink.id == active_share_link.id)
            .values(expires_at=datetime.now(tz=timezone.utc) - timedelta(days=1))
        )
        await session.commit()
    await engine.dispose()

    resp = await client.get(f"/api/shared/{active_share_link.token}")
    assert resp.status_code == 410
    data = resp.json()
    # FastAPI wraps the HTTPException detail dict inside {"detail": <value>},
    # so the actual body is {"detail": {"detail": "...", "expired": True}}.
    assert data["detail"]["expired"] is True


@pytest.mark.asyncio
async def test_public_access_revoked_token(
    client: AsyncClient,
    user_override: None,
    active_share_link: ShareLink,
) -> None:
    """11. Delete link, then GET → 404."""
    await client.delete(f"/api/share-links/{active_share_link.id}")
    resp = await client.get(f"/api/shared/{active_share_link.token}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_public_access_nonexistent_token(client: AsyncClient) -> None:
    """12. GET /api/shared/<random_token> that was never issued → 404."""
    resp = await client.get("/api/shared/nonexistent-token-that-does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_public_file_access_original(
    client: AsyncClient,
    active_share_link: ShareLink,
    test_job: Job,
    database_url: str,
    tmp_path: Path,
) -> None:
    """13. GET /api/shared/:token/files/:imageId/original → 200 image bytes."""
    # The test_job fixture stores display_path as an absolute path under
    # /storage which does not exist during tests.  We relocate it to
    # tmp_path before testing file serving so FileResponse can find the bytes.
    stub_file = tmp_path / "display.png"
    stub_file.write_bytes(b"PNG_STUB")

    engine = create_async_engine(database_url)
    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(ImageResult).where(ImageResult.job_id == test_job.id)
        )
        image_result = result.scalar_one()
        image_id = image_result.id
        # Point the display_path to the stub file we just created.
        image_result.display_path = str(stub_file)
        session.add(image_result)
        await session.commit()

    await engine.dispose()

    resp = await client.get(
        f"/api/shared/{active_share_link.token}/files/{image_id}/original"
    )
    assert resp.status_code == 200
    assert resp.content == b"PNG_STUB"


@pytest.mark.asyncio
async def test_public_file_access_wrong_image(
    client: AsyncClient,
    database_url: str,
    test_user: User,
    active_share_link: ShareLink,
) -> None:
    """14. GET /api/shared/:token/files/:otherId/original → 403.

    The requested image belongs to a *different* job than the one the token
    grants access to, so the server must reject the request with 403.
    """
    # Create a second job (not linked to the share link's job).
    engine = create_async_engine(database_url)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        other_job = Job(
            status=JobStatus.completed,
            pipeline_type="single_stage",
            model_arch="unet",
            owner_id=test_user.id,
        )
        session.add(other_job)
        await session.flush()

        other_image = ImageResult(
            job_id=other_job.id,
            original_filename="other.jpg",
            upload_path=f"/storage/{other_job.id}/upload.jpg",
            display_path=f"/storage/{other_job.id}/display.png",
            original_size={"width": 512, "height": 256},
        )
        session.add(other_image)
        await session.commit()
        other_image_id = other_image.id

    await engine.dispose()

    resp = await client.get(
        f"/api/shared/{active_share_link.token}/files/{other_image_id}/original"
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_public_file_access_mask_not_ready(
    client: AsyncClient,
    active_share_link: ShareLink,
    test_job: Job,
    database_url: str,
) -> None:
    """15. GET mask for an image without a mask_path → 404."""
    # The test_job fixture does not set mask_path, so it is NULL.
    engine = create_async_engine(database_url)
    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(ImageResult).where(ImageResult.job_id == test_job.id)
        )
        image_result = result.scalar_one()
        image_id = image_result.id
        # Confirm mask_path is indeed None.
        assert image_result.mask_path is None

    await engine.dispose()

    resp = await client.get(
        f"/api/shared/{active_share_link.token}/files/{image_id}/mask"
    )
    assert resp.status_code == 404


# ==============================================================================
# Rate limiting — test case 16
# ==============================================================================


@pytest.mark.asyncio
async def test_rate_limit_public_endpoint(
    client: AsyncClient,
    active_share_link: ShareLink,
) -> None:
    """Send 31 requests to the public endpoint; the 31st must return 429.

    slowapi tracks request counts per client IP.  The test client sends all
    requests from the same ``testclient`` address, so the counter accumulates
    across all 31 calls within this single test.
    """
    token = active_share_link.token
    responses = []
    for _ in range(31):
        resp = await client.get(f"/api/shared/{token}")
        responses.append(resp.status_code)

    # The first 30 should succeed (200); the 31st should be rate-limited (429).
    assert responses[-1] == 429, (
        f"Expected 429 on the 31st request, got {responses[-1]}. "
        f"All status codes: {responses}"
    )
