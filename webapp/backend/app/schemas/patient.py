"""Pydantic schemas for Patient request and response payloads.

Covers create, partial-update, list, and detail contracts.  The share
link types referenced in ``PatientDetailResponse`` are imported from
``app.schemas.share_link``; that module carries its own stable contract
and is kept separate to match the model split.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class CreatePatientRequest(BaseModel):
    """Validated body for ``POST /api/patients``."""

    full_name: str = Field(min_length=1, max_length=255)
    date_of_birth: date | None = None
    phone: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=5000)


class UpdatePatientRequest(BaseModel):
    """Validated body for ``PATCH /api/patients/{patient_id}``.

    All fields are optional.  The service layer uses ``model_fields_set``
    to determine which fields were explicitly supplied so that:

    - Omitting a field leaves the database column unchanged.
    - Explicitly sending ``null`` (e.g. ``"date_of_birth": null``) clears
      the column to NULL.

    This is the standard Pydantic v2 partial-update pattern.
    """

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    # date_of_birth, phone, and notes are all nullable — the service checks
    # model_fields_set to distinguish "not provided" from "set to null".
    date_of_birth: date | None = None
    phone: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=5000)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class PatientResponse(BaseModel):
    """Full patient payload returned by create, update, and detail endpoints.

    Excludes computed list-aggregation fields (``scan_count``, ``last_visit``)
    which are only needed in the paginated list surface.
    """

    id: uuid.UUID
    full_name: str
    date_of_birth: date | None
    phone: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PatientSummaryResponse(BaseModel):
    """Compact patient payload used by list and typeahead search endpoints.

    ``scan_count`` and ``last_visit`` are computed by correlated subqueries
    in the service layer rather than stored columns.
    """

    id: uuid.UUID
    full_name: str
    phone: str | None
    date_of_birth: date | None
    # Total number of inference jobs linked to this patient.
    scan_count: int
    # Timestamp of the most recently created linked job, or None if no jobs.
    last_visit: datetime | None


class PatientListQuery(BaseModel):
    """Query parameters for the patient list / typeahead endpoint."""

    # Free-text search: matched against full_name and phone via ILIKE.
    # An empty string returns all active patients.
    search: str = ""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class PatientsPageResponse(BaseModel):
    """Paginated envelope returned by ``GET /api/patients``."""

    items: list[PatientSummaryResponse]
    total_items: int
    page: int
    page_size: int
    total_pages: int
    has_previous_page: bool
    has_next_page: bool


class PatientJobSummary(BaseModel):
    """Compact job representation within a patient detail context.

    Intentionally lighter than ``JobSummaryResponse`` — only the fields
    relevant on the patient detail page are included.
    """

    id: uuid.UUID
    status: str
    pipeline_type: str
    model_arch: str
    image_count: int
    primary_filename: str
    created_at: datetime
    # True if at least one active (non-expired) share link exists for this job.
    # Always False in Phase 1; set to True by the share link service in Phase 2.
    has_share_link: bool


class PatientDetailResponse(BaseModel):
    """Full patient detail including linked jobs and active share links.

    ``share_links`` lists all active share links across this patient's jobs.
    In Phase 1 this list is always empty; it is populated by the share link
    service in Phase 2.
    """

    patient: PatientResponse
    # Most recent jobs first, limited to 20 by default.
    jobs: list[PatientJobSummary]
    # All active share links across this patient's jobs.
    share_links: list  # list[ShareLinkResponse] — typed as list to avoid
    # a circular import between schemas.  The concrete type is enforced
    # at the service layer which constructs ShareLinkResponse instances.
