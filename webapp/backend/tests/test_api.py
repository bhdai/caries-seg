"""Integration tests for Phase 2 — Core API.

Covered endpoints:
  POST /api/jobs            — file upload, DB persistence
  GET  /api/jobs/{id}       — full payload retrieval
  GET  /api/files/{id}/original — display-copy serving
  GET  /api/files/{id}/mask     — mask serving (404 until Phase 3)
"""

from __future__ import annotations

import uuid

import numpy as np
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import app.api.routes.jobs as jobs_routes

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_png_bytes(width: int = 64, height: int = 32) -> bytes:
    """Return the raw bytes of a minimal valid grayscale PNG.

    Uses cv2 to encode a blank image so the test does not depend on
    any third-party PNG library beyond what the backend already ships.
    """
    import cv2

    img = np.zeros((height, width, 3), dtype=np.uint8)
    # Add a white rectangle so the image is not entirely black, which
    # exercises the display-copy resize path more realistically.
    img[4:28, 4:60] = 255
    ok, buf = cv2.imencode(".png", img)
    assert ok, "cv2.imencode failed — test helper is broken"
    return buf.tobytes()


# ---------------------------------------------------------------------------
# POST /api/jobs
# ---------------------------------------------------------------------------


async def test_create_job_success(client: AsyncClient) -> None:
    """Uploading a valid PNG returns 202 with the initial job payload (status=pending)."""
    png_bytes = _make_png_bytes()
    response = await client.post(
        "/api/jobs",
        data={"pipeline_type": "single_stage", "model_arch": "unet"},
        files=[("files", ("xray.png", png_bytes, "image/png"))],
    )
    assert response.status_code == 202, response.text

    body = response.json()
    # The response is built before the background task runs; the job starts as pending.
    assert body["status"] == "pending"
    assert body["pipeline_type"] == "single_stage"
    assert body["model_arch"] == "unet"
    assert len(body["image_results"]) == 1

    result = body["image_results"][0]
    assert result["original_filename"] == "xray.png"
    assert result["original_size"] == {"width": 64, "height": 32}
    assert result["inference_time_ms"] is None
    assert result["bounding_boxes"] is None


async def test_create_job_multiple_files(client: AsyncClient) -> None:
    """Multiple files in one job each produce a separate ImageResult row."""
    png_bytes = _make_png_bytes()
    response = await client.post(
        "/api/jobs",
        data={"pipeline_type": "two_stage", "model_arch": "double_unet"},
        files=[
            ("files", ("a.png", png_bytes, "image/png")),
            ("files", ("b.png", png_bytes, "image/png")),
        ],
    )
    assert response.status_code == 202, response.text
    assert len(response.json()["image_results"]) == 2


async def test_create_job_file_too_large(client: AsyncClient) -> None:
    """A file exceeding 10 MB is rejected with 413 before any DB write."""
    # Create a >10 MB payload (11 MB of zero bytes wrapped in a valid PNG
    # is not needed; we just send raw bytes with a PNG content type — the
    # size check happens before image decoding).
    big_bytes = b"\x00" * (10 * 1024 * 1024 + 1)
    response = await client.post(
        "/api/jobs",
        data={"pipeline_type": "single_stage", "model_arch": "unet"},
        files=[("files", ("big.png", big_bytes, "image/png"))],
    )
    assert response.status_code == 413


async def test_create_job_invalid_mime(client: AsyncClient) -> None:
    """A file with a disallowed MIME type is rejected with 422."""
    response = await client.post(
        "/api/jobs",
        data={"pipeline_type": "single_stage", "model_arch": "unet"},
        files=[("files", ("doc.pdf", b"%PDF-1.4", "application/pdf"))],
    )
    assert response.status_code == 422


async def test_create_job_corrupt_image(client: AsyncClient) -> None:
    """Bytes that pass the MIME check but fail cv2.imdecode are rejected."""
    # Send 100 bytes with image/png content type — not a valid PNG.
    response = await client.post(
        "/api/jobs",
        data={"pipeline_type": "single_stage", "model_arch": "unet"},
        files=[("files", ("corrupt.png", b"\x89PNG\r\n" + b"\x00" * 94, "image/png"))],
    )
    assert response.status_code == 422


async def test_create_job_invalid_pipeline_type(client: AsyncClient) -> None:
    """An unrecognised pipeline_type is rejected with 422."""
    png_bytes = _make_png_bytes()
    response = await client.post(
        "/api/jobs",
        data={"pipeline_type": "unknown_pipeline", "model_arch": "unet"},
        files=[("files", ("xray.png", png_bytes, "image/png"))],
    )
    assert response.status_code == 422


async def test_create_job_rejects_path_like_filename(client: AsyncClient) -> None:
    """Path-like filenames are rejected instead of escaping the job directory."""
    png_bytes = _make_png_bytes()
    response = await client.post(
        "/api/jobs",
        data={"pipeline_type": "single_stage", "model_arch": "unet"},
        files=[("files", ("../escape.png", png_bytes, "image/png"))],
    )
    assert response.status_code == 422
    assert "directory components" in response.json()["detail"]


async def test_create_job_returns_500_when_display_copy_save_fails(
    client: AsyncClient,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Storage write failures return 500 and roll back the pending job rows."""
    png_bytes = _make_png_bytes()

    def _raise_storage_error(*args: object, **kwargs: object) -> object:
        raise jobs_routes.StorageError("boom")

    monkeypatch.setattr(jobs_routes, "save_display_copy", _raise_storage_error)

    response = await client.post(
        "/api/jobs",
        data={"pipeline_type": "single_stage", "model_arch": "unet"},
        files=[("files", ("xray.png", png_bytes, "image/png"))],
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to persist uploaded files."

    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            jobs_count = await connection.scalar(text("SELECT count(*) FROM jobs"))
            image_results_count = await connection.scalar(
                text("SELECT count(*) FROM image_results")
            )
    finally:
        await engine.dispose()

    assert jobs_count == 0
    assert image_results_count == 0


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}
# ---------------------------------------------------------------------------


async def test_get_job_success(client: AsyncClient) -> None:
    """GET /api/jobs/{id} returns the full job payload."""
    png_bytes = _make_png_bytes()
    create_resp = await client.post(
        "/api/jobs",
        data={"pipeline_type": "single_stage", "model_arch": "unet"},
        files=[("files", ("xray.png", png_bytes, "image/png"))],
    )
    assert create_resp.status_code == 202
    job_id = create_resp.json()["id"]

    get_resp = await client.get(f"/api/jobs/{job_id}")
    assert get_resp.status_code == 200

    body = get_resp.json()
    assert body["id"] == job_id
    # The background task may have run by now; accept any terminal/in-progress state.
    assert body["status"] in {"pending", "processing", "completed", "failed"}
    assert len(body["image_results"]) == 1


async def test_get_job_not_found(client: AsyncClient) -> None:
    """GET /api/jobs/{nonexistent_id} returns 404."""
    missing_id = uuid.uuid4()
    response = await client.get(f"/api/jobs/{missing_id}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/files/{image_result_id}/original
# ---------------------------------------------------------------------------


async def test_get_original_success(client: AsyncClient) -> None:
    """The display copy is served with Content-Type image/png."""
    png_bytes = _make_png_bytes()
    create_resp = await client.post(
        "/api/jobs",
        data={"pipeline_type": "single_stage", "model_arch": "unet"},
        files=[("files", ("xray.png", png_bytes, "image/png"))],
    )
    assert create_resp.status_code == 202
    result_id = create_resp.json()["image_results"][0]["id"]

    file_resp = await client.get(f"/api/files/{result_id}/original")
    assert file_resp.status_code == 200
    assert file_resp.headers["content-type"] == "image/png"
    assert len(file_resp.content) > 0


async def test_get_original_not_found(client: AsyncClient) -> None:
    """A nonexistent image_result_id returns 404."""
    missing_id = uuid.uuid4()
    response = await client.get(f"/api/files/{missing_id}/original")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/files/{image_result_id}/mask
# ---------------------------------------------------------------------------


async def test_get_mask_not_produced_yet(client: AsyncClient) -> None:
    """The mask endpoint returns 404 when inference has not produced a mask yet."""
    png_bytes = _make_png_bytes()
    create_resp = await client.post(
        "/api/jobs",
        data={"pipeline_type": "single_stage", "model_arch": "unet"},
        files=[("files", ("xray.png", png_bytes, "image/png"))],
    )
    assert create_resp.status_code == 202
    result_id = create_resp.json()["image_results"][0]["id"]

    mask_resp = await client.get(f"/api/files/{result_id}/mask")
    # mask_path is None until Phase 3 inference runs.
    assert mask_resp.status_code == 404
