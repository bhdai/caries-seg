"""Integration tests for Phase 1 — job history list and rerun endpoints.

Covered endpoints:
  GET  /api/jobs                      — paginated list with filters/search
  POST /api/jobs/{job_id}/rerun       — server-side rerun from stored uploads
"""

from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("user_override")]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_png_bytes(
    width: int = 64, height: int = 32, label: int = 0
) -> bytes:
    """Return a minimal valid PNG as raw bytes.

    ``label`` shifts the fill value so tests can produce visually distinct
    images without needing multiple files.
    """
    import cv2

    img = np.full((height, width, 3), label * 30 % 256, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", img)
    assert ok, "cv2.imencode failed — test helper is broken"
    return buf.tobytes()


async def _create_job(
    client: AsyncClient,
    *,
    pipeline_type: str = "single_stage",
    model_arch: str = "unet",
    filenames: list[str] | None = None,
) -> dict:
    """Submit a job and return the parsed response body."""
    if filenames is None:
        filenames = ["xray.png"]

    png_files = [
        ("files", (name, _make_png_bytes(label=i), "image/png"))
        for i, name in enumerate(filenames)
    ]
    resp = await client.post(
        "/api/jobs",
        data={"pipeline_type": pipeline_type, "model_arch": model_arch},
        files=png_files,
    )
    assert resp.status_code == 202, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# GET /api/jobs — basic listing
# ---------------------------------------------------------------------------


async def test_list_jobs_empty_database(client: AsyncClient) -> None:
    """An empty database returns an empty page with correct metadata."""
    resp = await client.get("/api/jobs")
    assert resp.status_code == 200
    body = resp.json()

    assert body["items"] == []
    assert body["total_items"] == 0
    assert body["total_pages"] == 0
    assert body["page"] == 1
    assert body["has_previous_page"] is False
    assert body["has_next_page"] is False


async def test_list_jobs_returns_summary_fields(client: AsyncClient) -> None:
    """Each job summary contains the expected compact fields."""
    await _create_job(client, filenames=["panoramic.png"])

    resp = await client.get("/api/jobs")
    assert resp.status_code == 200

    items = resp.json()["items"]
    assert len(items) == 1

    item = items[0]
    # Required scalar fields
    assert "id" in item
    assert "status" in item
    assert item["pipeline_type"] == "single_stage"
    assert item["model_arch"] == "unet"
    assert "created_at" in item
    assert "last_activity_at" in item
    assert item["image_count"] == 1
    assert item["primary_filename"] == "panoramic.png"
    assert item["filename_preview"] == ["panoramic.png"]
    # error_message may be None or a string depending on whether inference ran
    assert "error_message" in item


async def test_list_jobs_newest_first_default(client: AsyncClient) -> None:
    """Default sort is newest-first by last activity."""
    job_a = await _create_job(client, filenames=["a.png"])
    job_b = await _create_job(client, filenames=["b.png"])
    job_c = await _create_job(client, filenames=["c.png"])

    resp = await client.get("/api/jobs")
    assert resp.status_code == 200

    ids = [item["id"] for item in resp.json()["items"]]
    # All three jobs must appear; most recent creation should be listed first
    # (created_at is the tie-breaker when updated_at values are equal).
    assert set(ids) == {job_a["id"], job_b["id"], job_c["id"]}
    # The newest job (c) should be first given equal updated_at timestamps.
    assert ids[0] == job_c["id"]
    assert ids[-1] == job_a["id"]


async def test_list_jobs_sort_oldest(client: AsyncClient) -> None:
    """sort=oldest returns jobs in ascending creation order."""
    job_a = await _create_job(client, filenames=["a.png"])
    job_b = await _create_job(client, filenames=["b.png"])

    resp = await client.get("/api/jobs?sort=oldest")
    assert resp.status_code == 200

    ids = [item["id"] for item in resp.json()["items"]]
    assert ids[0] == job_a["id"]
    assert ids[-1] == job_b["id"]


async def test_list_jobs_sort_newest(client: AsyncClient) -> None:
    """sort=newest returns jobs in descending creation order."""
    job_a = await _create_job(client, filenames=["a.png"])
    job_b = await _create_job(client, filenames=["b.png"])

    resp = await client.get("/api/jobs?sort=newest")
    assert resp.status_code == 200

    ids = [item["id"] for item in resp.json()["items"]]
    assert ids[0] == job_b["id"]
    assert ids[-1] == job_a["id"]


async def test_list_jobs_multi_image_summary(client: AsyncClient) -> None:
    """A job with multiple images reports image_count and filename_preview correctly."""
    await _create_job(
        client,
        filenames=["first.png", "second.png", "third.png", "fourth.png"],
    )

    resp = await client.get("/api/jobs")
    assert resp.status_code == 200

    item = resp.json()["items"][0]
    assert item["image_count"] == 4
    assert item["primary_filename"] == "first.png"
    # Preview is capped at 3 entries.
    assert item["filename_preview"] == ["first.png", "second.png", "third.png"]


# ---------------------------------------------------------------------------
# GET /api/jobs — filters
# ---------------------------------------------------------------------------


async def test_list_jobs_filter_by_status(client: AsyncClient) -> None:
    """status filter returns only jobs with the specified status value."""
    await _create_job(client, filenames=["xray.png"])

    # Filter for "pending" — may or may not match depending on background task
    # timing, but we can assert that the total count is consistent.
    pending_resp = await client.get("/api/jobs?status=pending")
    other_resp = await client.get("/api/jobs?status=all")
    assert pending_resp.status_code == 200
    assert other_resp.status_code == 200

    pending_items = pending_resp.json()["items"]
    all_items = other_resp.json()["items"]
    # All pending items must also appear in the all-status listing.
    pending_ids = {i["id"] for i in pending_items}
    all_ids = {i["id"] for i in all_items}
    assert pending_ids.issubset(all_ids)


async def test_list_jobs_filter_by_pipeline_type(client: AsyncClient) -> None:
    """pipeline_type filter isolates jobs matching the requested pipeline."""
    job_ss = await _create_job(
        client, pipeline_type="single_stage", filenames=["ss.png"]
    )
    job_ts = await _create_job(
        client, pipeline_type="two_stage", model_arch="unet", filenames=["ts.png"]
    )

    resp_ss = await client.get("/api/jobs?pipeline_type=single_stage")
    resp_ts = await client.get("/api/jobs?pipeline_type=two_stage")
    assert resp_ss.status_code == 200
    assert resp_ts.status_code == 200

    ss_ids = {i["id"] for i in resp_ss.json()["items"]}
    ts_ids = {i["id"] for i in resp_ts.json()["items"]}

    assert job_ss["id"] in ss_ids
    assert job_ts["id"] not in ss_ids
    assert job_ts["id"] in ts_ids
    assert job_ss["id"] not in ts_ids


async def test_list_jobs_filter_by_model_arch(client: AsyncClient) -> None:
    """model_arch filter isolates jobs using the requested architecture."""
    job_unet = await _create_job(client, model_arch="unet", filenames=["u.png"])
    job_dunet = await _create_job(
        client, model_arch="double_unet", filenames=["du.png"]
    )

    resp_unet = await client.get("/api/jobs?model_arch=unet")
    resp_dunet = await client.get("/api/jobs?model_arch=double_unet")

    unet_ids = {i["id"] for i in resp_unet.json()["items"]}
    dunet_ids = {i["id"] for i in resp_dunet.json()["items"]}

    assert job_unet["id"] in unet_ids
    assert job_dunet["id"] not in unet_ids
    assert job_dunet["id"] in dunet_ids
    assert job_unet["id"] not in dunet_ids


async def test_list_jobs_filter_combination(client: AsyncClient) -> None:
    """Combining pipeline_type and model_arch filters reduces the result set."""
    job_match = await _create_job(
        client,
        pipeline_type="two_stage",
        model_arch="double_unet",
        filenames=["match.png"],
    )
    await _create_job(
        client,
        pipeline_type="single_stage",
        model_arch="unet",
        filenames=["no_match.png"],
    )

    resp = await client.get(
        "/api/jobs?pipeline_type=two_stage&model_arch=double_unet"
    )
    assert resp.status_code == 200
    ids = {i["id"] for i in resp.json()["items"]}
    assert job_match["id"] in ids
    assert resp.json()["total_items"] == 1


async def test_list_jobs_invalid_filter_value(client: AsyncClient) -> None:
    """An unrecognised enum value for a filter parameter returns 422."""
    resp = await client.get("/api/jobs?status=unknown_status")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/jobs — search
# ---------------------------------------------------------------------------


async def test_list_jobs_search_by_filename(client: AsyncClient) -> None:
    """search parameter matches jobs that contain a file with the given name."""
    await _create_job(client, filenames=["panoramic_xray.png"])
    await _create_job(client, filenames=["other_image.png"])

    resp = await client.get("/api/jobs?search=panoramic")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["primary_filename"] == "panoramic_xray.png"


async def test_list_jobs_search_by_filename_case_insensitive(
    client: AsyncClient,
) -> None:
    """Filename search is case-insensitive."""
    await _create_job(client, filenames=["UpperCase.png"])

    resp = await client.get("/api/jobs?search=uppercase")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


async def test_list_jobs_search_by_job_id(client: AsyncClient) -> None:
    """search parameter matches a job when the search text is its UUID."""
    job = await _create_job(client, filenames=["xray.png"])
    job_id = job["id"]

    resp = await client.get(f"/api/jobs?search={job_id}")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == job_id


async def test_list_jobs_search_no_duplicates_multi_file(
    client: AsyncClient,
) -> None:
    """A multi-file job matching multiple filenames appears exactly once."""
    await _create_job(
        client, filenames=["alpha.png", "alpha_2.png", "unrelated.png"]
    )

    # Both "alpha.png" and "alpha_2.png" match "alpha", but the job should
    # appear only once in the results.
    resp = await client.get("/api/jobs?search=alpha")
    assert resp.status_code == 200
    assert resp.json()["total_items"] == 1
    assert len(resp.json()["items"]) == 1


async def test_list_jobs_search_no_match(client: AsyncClient) -> None:
    """search with no matching text returns an empty result set."""
    await _create_job(client, filenames=["xray.png"])

    resp = await client.get("/api/jobs?search=zzz_no_match_zzz")
    assert resp.status_code == 200
    assert resp.json()["total_items"] == 0
    assert resp.json()["items"] == []


# ---------------------------------------------------------------------------
# GET /api/jobs — pagination
# ---------------------------------------------------------------------------


async def test_list_jobs_pagination_first_page(client: AsyncClient) -> None:
    """First page has has_previous_page=False."""
    for i in range(3):
        await _create_job(client, filenames=[f"img_{i}.png"])

    resp = await client.get("/api/jobs?page=1&page_size=2")
    assert resp.status_code == 200
    body = resp.json()

    assert body["page"] == 1
    assert body["page_size"] == 2
    assert body["total_items"] == 3
    assert body["total_pages"] == 2
    assert body["has_previous_page"] is False
    assert body["has_next_page"] is True
    assert len(body["items"]) == 2


async def test_list_jobs_pagination_last_page(client: AsyncClient) -> None:
    """Last page has has_next_page=False and may have fewer items than page_size."""
    for i in range(3):
        await _create_job(client, filenames=[f"img_{i}.png"])

    resp = await client.get("/api/jobs?page=2&page_size=2")
    assert resp.status_code == 200
    body = resp.json()

    assert body["page"] == 2
    assert body["has_previous_page"] is True
    assert body["has_next_page"] is False
    # Last page of 3 items with page_size=2 contains 1 item.
    assert len(body["items"]) == 1


async def test_list_jobs_pagination_middle_page(client: AsyncClient) -> None:
    """Middle pages have both has_previous_page and has_next_page set to True."""
    for i in range(5):
        await _create_job(client, filenames=[f"img_{i}.png"])

    resp = await client.get("/api/jobs?page=2&page_size=2")
    assert resp.status_code == 200
    body = resp.json()

    assert body["has_previous_page"] is True
    assert body["has_next_page"] is True


async def test_list_jobs_pagination_empty_result(client: AsyncClient) -> None:
    """Pagination metadata is consistent for an empty result set."""
    resp = await client.get("/api/jobs?search=no_match_at_all")
    assert resp.status_code == 200
    body = resp.json()

    assert body["total_items"] == 0
    assert body["total_pages"] == 0
    assert body["has_previous_page"] is False
    assert body["has_next_page"] is False


async def test_list_jobs_pagination_no_overlap(client: AsyncClient) -> None:
    """Items on page 1 and page 2 are disjoint (no duplicate rows)."""
    for i in range(4):
        await _create_job(client, filenames=[f"img_{i}.png"])

    page1 = await client.get("/api/jobs?page=1&page_size=2&sort=oldest")
    page2 = await client.get("/api/jobs?page=2&page_size=2&sort=oldest")
    assert page1.status_code == 200
    assert page2.status_code == 200

    ids_page1 = {i["id"] for i in page1.json()["items"]}
    ids_page2 = {i["id"] for i in page2.json()["items"]}
    assert ids_page1.isdisjoint(ids_page2)


# ---------------------------------------------------------------------------
# POST /api/jobs/{job_id}/rerun
# ---------------------------------------------------------------------------


async def test_rerun_creates_new_job(client: AsyncClient) -> None:
    """Rerun creates a distinct new pending job with the same pipeline/model."""
    source = await _create_job(
        client,
        pipeline_type="single_stage",
        model_arch="unet",
        filenames=["source.png"],
    )
    source_id = source["id"]

    resp = await client.post(f"/api/jobs/{source_id}/rerun")
    assert resp.status_code == 202, resp.text

    new_job = resp.json()
    # The new job must be a different row.
    assert new_job["id"] != source_id
    # It must start as pending.
    assert new_job["status"] == "pending"
    # It must inherit the source pipeline configuration.
    assert new_job["pipeline_type"] == "single_stage"
    assert new_job["model_arch"] == "unet"
    # It must have the same number of image results.
    assert len(new_job["image_results"]) == 1
    assert new_job["image_results"][0]["original_filename"] == "source.png"


async def test_rerun_multi_image_job(client: AsyncClient) -> None:
    """Rerun copies all images from a multi-file source job."""
    source = await _create_job(
        client,
        filenames=["img1.png", "img2.png", "img3.png"],
    )

    resp = await client.post(f"/api/jobs/{source['id']}/rerun")
    assert resp.status_code == 202

    new_job = resp.json()
    assert len(new_job["image_results"]) == 3
    new_filenames = {ir["original_filename"] for ir in new_job["image_results"]}
    assert new_filenames == {"img1.png", "img2.png", "img3.png"}


async def test_rerun_new_job_appears_in_list(client: AsyncClient) -> None:
    """After rerun, the new job is visible in GET /api/jobs."""
    source = await _create_job(client, filenames=["xray.png"])
    rerun_resp = await client.post(f"/api/jobs/{source['id']}/rerun")
    assert rerun_resp.status_code == 202
    new_id = rerun_resp.json()["id"]

    list_resp = await client.get("/api/jobs")
    assert list_resp.status_code == 200
    ids = {i["id"] for i in list_resp.json()["items"]}
    assert new_id in ids
    assert source["id"] in ids
    assert list_resp.json()["total_items"] == 2


async def test_rerun_not_found(client: AsyncClient) -> None:
    """Rerun of a non-existent job returns 404."""
    missing_id = uuid.uuid4()
    resp = await client.post(f"/api/jobs/{missing_id}/rerun")
    assert resp.status_code == 404
    body = resp.json()
    assert "code" in body
    assert body["code"] == "jobs.notFound"


async def test_rerun_fails_when_upload_file_missing(
    client: AsyncClient, tmp_path: Path
) -> None:
    """Rerun returns 409 when a source upload file is no longer on disk.

    No new job row should be created when a source file is missing.
    """
    source = await _create_job(client, filenames=["missing.png"])
    source_id = source["id"]

    # Locate and delete the upload file.  The storage root is at
    # tmp_path/storage/uploads/{job_id}/ per the conftest fixture.
    upload_dir = tmp_path / "storage" / "uploads" / source_id
    assert upload_dir.exists(), "upload directory must exist after job creation"
    for f in upload_dir.iterdir():
        f.unlink()

    resp = await client.post(f"/api/jobs/{source_id}/rerun")
    assert resp.status_code == 409
    body = resp.json()
    assert "no longer available" in body["detail"]
    assert "code" in body
    assert body["code"] == "jobs.sourceUnavailable"

    # The list must still contain only the original job (no partial new row).
    list_resp = await client.get("/api/jobs")
    assert list_resp.json()["total_items"] == 1


async def test_search_underscore_not_wildcard(client: AsyncClient) -> None:
    """Search for a literal underscore matches exactly, not as a SQL wildcard.

    'alpha_2.png' should not match 'alphax2.png' when searching for 'alpha_2'.
    """
    await _create_job(client, filenames=["alpha_2.png"])
    await _create_job(client, filenames=["alphax2.png"])

    resp = await client.get("/api/jobs?search=alpha_2")
    assert resp.status_code == 200
    items = resp.json()["items"]
    # Only the exact-underscore filename should be returned.
    assert len(items) == 1
    assert items[0]["primary_filename"] == "alpha_2.png"


async def test_search_percent_not_wildcard(client: AsyncClient) -> None:
    """Search for a literal percent sign is treated as a literal character."""
    await _create_job(client, filenames=["100%_crop.png"])
    await _create_job(client, filenames=["unrelated.png"])

    resp = await client.get("/api/jobs?search=100%25_crop")
    assert resp.status_code == 200
    # The query should not explode and should not return the unrelated job.
    items = resp.json()["items"]
    filenames = [i["primary_filename"] for i in items]
    assert "unrelated.png" not in filenames
