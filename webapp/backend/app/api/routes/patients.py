"""Route handlers for all patient-related endpoints.

Endpoints
---------
POST   /api/patients                   Create a new patient record.
GET    /api/patients                   List active patients (paginated, searchable).
GET    /api/patients/{patient_id}      Full detail for a single patient.
PATCH  /api/patients/{patient_id}      Partial update of patient fields.
DELETE /api/patients/{patient_id}      Soft-delete a patient (admin only).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user, require_admin
from app.core.database import get_db
from app.models.user import User
from app.schemas.patient import (
    CreatePatientRequest,
    PatientDetailResponse,
    PatientListQuery,
    PatientResponse,
    PatientsPageResponse,
    UpdatePatientRequest,
)
import app.services.patients as patients_service

# All routes in this router require an authenticated user.  Admin-only
# routes add an extra ``require_admin`` dependency at the handler level.
router = APIRouter(prefix="/patients", dependencies=[Depends(get_current_user)])


# ---------------------------------------------------------------------------
# POST /api/patients
# ---------------------------------------------------------------------------


@router.post("", status_code=201, response_model=PatientResponse)
async def create_patient(
    body: CreatePatientRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
) -> PatientResponse:
    """Create a new patient record.

    No uniqueness check on ``full_name`` — different patients may share names.

    Returns:
        HTTP 201 with the full ``PatientResponse`` payload.

    Raises:
        HTTPException 422: Validation failure (e.g. empty ``full_name``).
    """
    patient = await patients_service.create_patient(body, db)
    return PatientResponse.model_validate(patient)


# ---------------------------------------------------------------------------
# GET /api/patients
# ---------------------------------------------------------------------------


def _parse_patient_list_query(
    search: Annotated[str, Query(max_length=200)] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PatientListQuery:
    """Construct a validated ``PatientListQuery`` from individual query parameters.

    Exposed as a dependency factory so FastAPI surfaces each parameter in the
    OpenAPI schema and validates bounds before the handler runs.
    """
    return PatientListQuery(search=search, page=page, page_size=page_size)


@router.get("", response_model=PatientsPageResponse)
async def list_patients(
    query: Annotated[PatientListQuery, Depends(_parse_patient_list_query)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
) -> PatientsPageResponse:
    """Return a paginated, searchable list of active patients.

    Patients with ``deleted_at IS NOT NULL`` are excluded.

    Query parameters
    ----------------
    search    : Free-text match against name or phone (ILIKE, default "").
    page      : 1-based page number (default 1).
    page_size : Items per page, 1–100 (default 20).
    """
    return await patients_service.list_patients(query, db)


# ---------------------------------------------------------------------------
# GET /api/patients/{patient_id}
# ---------------------------------------------------------------------------


@router.get("/{patient_id}", response_model=PatientDetailResponse)
async def get_patient(
    patient_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
) -> PatientDetailResponse:
    """Return full patient detail including linked jobs and active share links.

    Raises:
        HTTPException 404: Patient not found or has been soft-deleted.
    """
    return await patients_service.get_patient_detail(patient_id, db)


# ---------------------------------------------------------------------------
# PATCH /api/patients/{patient_id}
# ---------------------------------------------------------------------------


@router.patch("/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: uuid.UUID,
    body: UpdatePatientRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
) -> PatientResponse:
    """Apply a partial update to a patient record.

    Only fields present in the request body are written; omitted fields
    retain their current values.  Send ``null`` explicitly to clear a
    nullable field.

    Returns:
        HTTP 200 with the updated ``PatientResponse`` payload.

    Raises:
        HTTPException 404: Patient not found or has been soft-deleted.
    """
    patient = await patients_service.update_patient(patient_id, body, db)
    return PatientResponse.model_validate(patient)


# ---------------------------------------------------------------------------
# DELETE /api/patients/{patient_id}   (admin only)
# ---------------------------------------------------------------------------


@router.delete("/{patient_id}", status_code=204)
async def delete_patient(
    patient_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _admin: Annotated[User, Depends(require_admin)],
) -> None:
    """Soft-delete a patient by setting ``deleted_at`` to the current time.

    Linked jobs retain their ``patient_id`` FK for historical audit.

    Returns:
        HTTP 204 No Content on success.

    Raises:
        HTTPException 400: Patient has already been soft-deleted.
        HTTPException 403: Caller is not an admin.
        HTTPException 404: Patient not found.
    """
    await patients_service.soft_delete_patient(patient_id, db)
