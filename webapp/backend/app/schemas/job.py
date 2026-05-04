"""Pydantic schemas for ``Job`` request and response payloads."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.image_result import ImageResultResponse


class JobResponse(BaseModel):
    """Full job payload returned by both ``POST /api/jobs`` and
    ``GET /api/jobs/{id}``."""

    id: uuid.UUID
    status: str
    pipeline_type: str
    model_arch: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    image_results: list[ImageResultResponse]
    # Populated when the job is linked to a patient; None otherwise.
    patient_id: uuid.UUID | None = None
    patient_name: str | None = None

    model_config = {"from_attributes": True}


class PatchJobRequest(BaseModel):
    """Validated body for ``PATCH /api/jobs/{job_id}``.

    Sending ``patient_id=<uuid>`` links the job to that patient.
    Sending ``patient_id=null`` removes any existing link.
    """

    patient_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Form field types
#
# Defined as type aliases here so that the route handler can annotate form
# fields with Literal constraints without importing typing/Literal directly
# in the routes module.
# ---------------------------------------------------------------------------
PipelineTypeField = Literal["single_stage", "two_stage"]
ModelArchField = Literal["unet", "double_unet"]
