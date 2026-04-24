"""Pydantic schemas for the job history list and rerun endpoints.

Separate from ``schemas/job.py`` so the full job detail contract stays
stable while the history list interface can evolve independently.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Filter / query parameter types
# ---------------------------------------------------------------------------

StatusFilter = Literal["pending", "processing", "completed", "failed", "all"]
PipelineFilter = Literal["single_stage", "two_stage", "all"]
ModelFilter = Literal["unet", "double_unet", "all"]
SortOrder = Literal["newest", "oldest", "last_activity_desc"]


class JobListQuery(BaseModel):
    """Normalize and validate history query parameters for list endpoints.

    This model defines the only supported filters so the API surface remains
    explicit, stable, and forward-compatible with later auth scoping.
    """

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    status: StatusFilter = "all"
    pipeline_type: PipelineFilter = "all"
    model_arch: ModelFilter = "all"
    search: str | None = None
    sort: SortOrder = "last_activity_desc"


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class JobSummaryResponse(BaseModel):
    """Represent the compact job payload used by dashboard and history surfaces.

    The response intentionally excludes full image-result detail so list pages
    stay small, cacheable, and stable under pagination.
    """

    id: uuid.UUID
    status: str
    pipeline_type: str
    model_arch: str
    created_at: datetime
    last_activity_at: datetime
    image_count: int
    primary_filename: str
    filename_preview: list[str]
    error_message: str | None


class JobsPageResponse(BaseModel):
    """Return one server-side page of job summaries together with enough
    pagination metadata for a URL-synchronized list UI.
    """

    items: list[JobSummaryResponse]
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_previous_page: bool
    has_next_page: bool
