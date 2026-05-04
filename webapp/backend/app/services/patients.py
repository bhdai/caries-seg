"""Service layer for patient CRUD operations.

Provides the canonical query logic for creating, listing, updating, and
soft-deleting patient records.  Route handlers call these functions and
remain thin HTTP-boundary translators.

All active-patient queries filter ``WHERE deleted_at IS NULL``.  Soft-deleted
patients are invisible to list/search/detail endpoints but their linked jobs
retain the ``patient_id`` FK for historical audit.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AppError
from app.models.image_result import ImageResult
from app.models.job import Job
from app.models.patient import Patient
from app.services.share_links import list_share_links_for_patient
from app.schemas.patient import (
    CreatePatientRequest,
    PatientDetailResponse,
    PatientJobSummary,
    PatientListQuery,
    PatientResponse,
    PatientsPageResponse,
    PatientSummaryResponse,
    UpdatePatientRequest,
)

# ---------------------------------------------------------------------------
# Wildcard-escape constant — mirrors the pattern used in services/jobs.py.
# ---------------------------------------------------------------------------
_ILIKE_ESCAPE = "\\"


def _escape_ilike(term: str) -> str:
    """Escape SQL wildcard characters in a user-supplied search term.

    Backslash must be escaped first to avoid double-escaping.
    """
    return (
        term
        .replace(_ILIKE_ESCAPE, _ILIKE_ESCAPE * 2)  # escape literal \
        .replace("%", f"{_ILIKE_ESCAPE}%")           # escape wildcard %
        .replace("_", f"{_ILIKE_ESCAPE}_")           # escape wildcard _
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def create_patient(data: CreatePatientRequest, db: AsyncSession) -> Patient:
    """Insert a new Patient row and return the created ORM instance.

    No uniqueness check on ``full_name`` — different patients may share names.

    Args:
        data: Validated creation payload.
        db: Active async database session.

    Returns:
        The newly created Patient ORM instance with all server-generated
        fields populated after the flush.
    """
    patient = Patient(
        full_name=data.full_name,
        date_of_birth=data.date_of_birth,
        phone=data.phone,
        notes=data.notes,
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)
    return patient


# ---------------------------------------------------------------------------
# List with search and computed aggregation fields
# ---------------------------------------------------------------------------


async def list_patients(
    query: PatientListQuery,
    db: AsyncSession,
) -> PatientsPageResponse:
    """Return a paginated list of active patients with computed job aggregates.

    Search is applied to ``full_name`` and ``phone`` via case-insensitive
    ILIKE.  Results are sorted alphabetically by ``full_name``, with ``id``
    as a stable tie-breaker for deterministic pagination.

    ``scan_count`` and ``last_visit`` are computed via correlated subqueries
    so no extra round-trip is required and the aggregates stay in sync with
    the live ``jobs`` table.

    Args:
        query: Validated filter and pagination parameters.
        db: Active async database session.

    Returns:
        A single page of patient summaries with pagination metadata.
    """
    # ==============================================================================
    # Build the base active-patient predicate.
    #
    # All queries against the patients table must filter deleted_at IS NULL
    # so soft-deleted patients are invisible to all list/search surfaces.
    # ==============================================================================
    filters = [Patient.deleted_at.is_(None)]

    if query.search:
        search_term = f"%{_escape_ilike(query.search)}%"
        filters.append(
            or_(
                Patient.full_name.ilike(search_term, escape=_ILIKE_ESCAPE),
                Patient.phone.ilike(search_term, escape=_ILIKE_ESCAPE),
            )
        )

    # ==============================================================================
    # Correlated subqueries for scan_count and last_visit.
    #
    # Each subquery runs once per result row.  For moderate patient counts
    # (<5K rows) this is sub-millisecond.  A materialised column or index
    # can be added later if profiling shows this is a bottleneck.
    # ==============================================================================
    scan_count_sq = (
        select(func.count(Job.id))
        .where(Job.patient_id == Patient.id)
        .correlate(Patient)
        .scalar_subquery()
    )
    last_visit_sq = (
        select(func.max(Job.created_at))
        .where(Job.patient_id == Patient.id)
        .correlate(Patient)
        .scalar_subquery()
    )

    # ==============================================================================
    # Count total matching patients before applying pagination.
    # ==============================================================================
    count_q = select(func.count(Patient.id))
    for f in filters:
        count_q = count_q.where(f)
    total_items: int = (await db.execute(count_q)).scalar_one()

    # ==============================================================================
    # Build the page query.
    # ==============================================================================
    q = (
        select(
            Patient,
            scan_count_sq.label("scan_count"),
            last_visit_sq.label("last_visit"),
        )
        .order_by(Patient.full_name.asc(), Patient.id.asc())
    )
    for f in filters:
        q = q.where(f)

    offset = (query.page - 1) * query.page_size
    q = q.offset(offset).limit(query.page_size)

    rows = (await db.execute(q)).all()

    items: list[PatientSummaryResponse] = [
        PatientSummaryResponse(
            id=row.Patient.id,
            full_name=row.Patient.full_name,
            phone=row.Patient.phone,
            date_of_birth=row.Patient.date_of_birth,
            scan_count=row.scan_count,
            last_visit=row.last_visit,
        )
        for row in rows
    ]

    total_pages = math.ceil(total_items / query.page_size) if total_items > 0 else 0

    return PatientsPageResponse(
        items=items,
        total_items=total_items,
        page=query.page,
        page_size=query.page_size,
        total_pages=total_pages,
        has_previous_page=query.page > 1,
        has_next_page=query.page < total_pages,
    )


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


async def get_patient_detail(
    patient_id: uuid.UUID,
    db: AsyncSession,
    settings: Settings,
) -> PatientDetailResponse:
    """Return full patient detail including linked jobs and active share links.

    Jobs are returned most-recent-first (by ``created_at``), limited to 20.

    Args:
        patient_id: UUID of the patient to load.
        db: Active async database session.
        settings: Application settings used to map share-link rows.

    Raises:
        AppError 404: Patient not found or has been soft-deleted.
    """
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.deleted_at.is_(None))
    )
    patient = result.scalar_one_or_none()
    if patient is None:
        raise AppError(
            status_code=404,
            code="patients.notFound",
            detail=f"Patient {patient_id} not found.",
        )

    # Load the 20 most recent linked jobs for the detail page.
    jobs_result = await db.execute(
        select(Job)
        .where(Job.patient_id == patient_id)
        .order_by(Job.created_at.desc())
        .limit(20)
    )
    jobs = list(jobs_result.scalars().all())

    share_links = await list_share_links_for_patient(patient_id, db, settings)
    active_share_link_job_ids = {
        link.job_id for link in share_links if link.is_active
    }

    job_summaries: list[PatientJobSummary] = []
    for job in jobs:
        filenames = [image.original_filename for image in job.image_results]
        job_summaries.append(
            PatientJobSummary(
                id=job.id,
                status=job.status,
                pipeline_type=job.pipeline_type,
                model_arch=job.model_arch,
                created_at=job.created_at,
                last_activity_at=job.updated_at,
                image_count=len(job.image_results),
                primary_filename=filenames[0] if filenames else "",
                filename_preview=filenames[:3],
                error_message=job.error_message,
                patient_id=job.patient_id,
                patient_name=job.patient_name,
                has_share_link=job.id in active_share_link_job_ids,
            )
        )

    return PatientDetailResponse(
        id=patient.id,
        full_name=patient.full_name,
        date_of_birth=patient.date_of_birth,
        phone=patient.phone,
        notes=patient.notes,
        created_at=patient.created_at,
        updated_at=patient.updated_at,
        jobs=job_summaries,
        share_links=share_links,
    )


# ---------------------------------------------------------------------------
# Update (partial)
# ---------------------------------------------------------------------------


async def update_patient(
    patient_id: uuid.UUID,
    data: UpdatePatientRequest,
    db: AsyncSession,
) -> Patient:
    """Apply a partial update to a patient record.

    Only fields present in ``data.model_fields_set`` are written.  This
    preserves the distinction between "not provided" (skip) and
    "explicitly set to null" (clear the column).

    Args:
        patient_id: UUID of the patient to update.
        data: Partial update payload.
        db: Active async database session.

    Returns:
        The updated Patient ORM instance.

    Raises:
        AppError 404: Patient not found or has been soft-deleted.
    """
    result = await db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.deleted_at.is_(None))
    )
    patient = result.scalar_one_or_none()
    if patient is None:
        raise AppError(
            status_code=404,
            code="patients.notFound",
            detail=f"Patient {patient_id} not found.",
        )

    # Apply only the fields the caller explicitly included in the request body.
    for field_name in data.model_fields_set:
        setattr(patient, field_name, getattr(data, field_name))

    await db.commit()
    await db.refresh(patient)
    return patient


# ---------------------------------------------------------------------------
# Soft-delete
# ---------------------------------------------------------------------------


async def soft_delete_patient(patient_id: uuid.UUID, db: AsyncSession) -> None:
    """Soft-delete a patient by stamping ``deleted_at`` with the current time.

    Linked jobs retain their ``patient_id`` FK for historical audit; they
    are not modified by this operation.

    Args:
        patient_id: UUID of the patient to archive.
        db: Active async database session.

    Raises:
        AppError 404: Patient does not exist (active or deleted).
        AppError 400: Patient has already been soft-deleted.
    """
    # Load without the deleted_at IS NULL guard so we can return a 400 for
    # already-deleted patients rather than a misleading 404.
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if patient is None:
        raise AppError(
            status_code=404,
            code="patients.notFound",
            detail=f"Patient {patient_id} not found.",
        )

    if patient.deleted_at is not None:
        raise AppError(
            status_code=400,
            code="patients.alreadyDeleted",
            detail="Patient has already been deleted.",
        )

    patient.deleted_at = datetime.now(tz=timezone.utc)
    await db.commit()
