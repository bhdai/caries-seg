"""Service layer for share link creation, revocation, and public access.

All database operations for the ``share_links`` table live here so that
route handlers remain thin HTTP-boundary translators.

Design notes
------------
- Tokens are generated with ``secrets.token_urlsafe(32)`` (192 bits of
  entropy), making brute-force enumeration computationally infeasible.
- The UNIQUE constraint on ``share_links.token`` is the safety net against
  the astronomically unlikely token collision: the database will raise an
  IntegrityError that the caller can catch and retry.
- ``get_public_result`` deliberately does NOT filter ``deleted_at IS NULL``
  when loading the patient.  A share link issued before a patient was
  soft-deleted must still show the patient name so the result page is
  meaningful to the patient who received the printed QR code.
- PII logging policy: only ``token`` (a random opaque string) and
  ``job_id`` are logged for access auditing.  Patient names, usernames, and
  other PII are never written to logs.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.exceptions import AppError
from app.models.image_result import ImageResult
from app.models.job import Job
from app.models.patient import Patient
from app.models.share_link import ShareLink
from app.models.user import User, UserRole
from app.schemas.share_link import (
    ShareLinkResponse,
    SharedImageResult,
    SharedResultResponse,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# Internal helpers
# ==============================================================================


def _build_share_link_response(link: ShareLink, settings: Settings) -> ShareLinkResponse:
    """Construct a ``ShareLinkResponse`` from an ORM ``ShareLink`` instance.

    The ``url`` and ``is_expired`` fields are derived here rather than stored
    in the database, so this helper centralises the computation in one place.
    """
    now = datetime.now(tz=timezone.utc)
    is_expired = (
        link.expires_at is not None
        and link.expires_at.replace(tzinfo=timezone.utc) < now
    )
    return ShareLinkResponse(
        id=link.id,
        job_id=link.job_id,
        token=link.token,
        url=f"{settings.FRONTEND_URL}/shared/{link.token}",
        expires_at=link.expires_at,
        is_expired=is_expired,
        created_at=link.created_at,
        created_by_username=(
            link.created_by.username if link.created_by is not None else None
        ),
    )


def _check_job_ownership(job: Job, user: User) -> None:
    """Raise 403 if ``user`` does not own ``job`` and is not an admin.

    Orphaned jobs (``owner_id=None``) are also treated as inaccessible by
    non-admin users, consistent with the existing files and jobs service
    ownership model.
    """
    if user.role == UserRole.admin:
        return
    if job.owner_id != user.id:
        raise AppError(
            status_code=403,
            code="share_links.accessDenied",
            detail="You do not have permission to manage share links for this job.",
        )


async def _load_active_share_link(job_id: uuid.UUID, db: AsyncSession) -> ShareLink | None:
    """Query the single active share link for ``job_id``, if one exists.

    A link is considered *active* when it has no expiry (``expires_at IS NULL``)
    or its expiry is in the future.  Expired links are not returned.
    """
    now = datetime.now(tz=timezone.utc)
    result = await db.execute(
        select(ShareLink)
        .where(ShareLink.job_id == job_id)
        .where(
            # IS NULL means never-expiring; otherwise compare against now.
            (ShareLink.expires_at.is_(None)) | (ShareLink.expires_at > now)
        )
        # There should be at most one active link per job, but LIMIT 1 is a
        # safety guard against any hypothetical data inconsistency.
        .limit(1)
    )
    return result.scalar_one_or_none()


# ==============================================================================
# Authenticated operations
# ==============================================================================


async def create_share_link(
    job_id: uuid.UUID,
    expires_in_days: int | None,
    user: User,
    db: AsyncSession,
    settings: Settings,
) -> ShareLinkResponse:
    """Create a new share link for ``job_id``, or return the existing active one.

    The operation is idempotent: if an active share link already exists for
    this job it is returned unchanged.  This prevents duplicate link rows
    when a doctor clicks "Generate Link" more than once without revoking.

    Args:
        job_id: UUID of the job whose results are to be shared.
        expires_in_days: Days until the link expires.  None means no expiry.
        user: The authenticated user performing the action.
        db: Active async database session.
        settings: Application settings (provides ``FRONTEND_URL``).

    Returns:
        A ``ShareLinkResponse`` for the active share link (new or existing).

    Raises:
        AppError 404: Job not found.
        AppError 403: Caller does not own the job (non-admin).
    """
    # Load the job to check existence and ownership.
    job_result = await db.execute(select(Job).where(Job.id == job_id))
    job = job_result.scalar_one_or_none()
    if job is None:
        raise AppError(
            status_code=404,
            code="share_links.jobNotFound",
            detail=f"Job {job_id} not found.",
        )

    _check_job_ownership(job, user)

    # Return the existing active link to preserve idempotency.
    existing = await _load_active_share_link(job_id, db)
    if existing is not None:
        # Eagerly load created_by so _build_share_link_response can read
        # the username without triggering lazy-load on the closed session.
        await db.refresh(existing, ["created_by"])
        logger.info(
            "Returning existing active share link: token=%s job_id=%s",
            existing.token,
            job_id,
        )
        return _build_share_link_response(existing, settings)

    # Generate a cryptographically strong token.
    token = secrets.token_urlsafe(32)

    # Compute the expiry timestamp in UTC.
    expires_at: datetime | None = None
    if expires_in_days is not None:
        expires_at = datetime.now(tz=timezone.utc) + timedelta(days=expires_in_days)

    link = ShareLink(
        job_id=job_id,
        token=token,
        expires_at=expires_at,
        created_by_id=user.id,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link, ["created_by"])

    logger.info(
        "Created share link: token=%s job_id=%s",
        token,
        job_id,
    )
    return _build_share_link_response(link, settings)


async def get_share_link_for_job(
    job_id: uuid.UUID,
    user: User,
    db: AsyncSession,
    settings: Settings,
) -> ShareLinkResponse | None:
    """Return the active share link for ``job_id``, or None if none exists.

    Args:
        job_id: UUID of the job to query.
        user: The authenticated user performing the action.
        db: Active async database session.
        settings: Application settings (provides ``FRONTEND_URL``).

    Returns:
        A ``ShareLinkResponse`` for the active link, or ``None``.

    Raises:
        AppError 404: Job not found.
        AppError 403: Caller does not own the job (non-admin).
    """
    job_result = await db.execute(select(Job).where(Job.id == job_id))
    job = job_result.scalar_one_or_none()
    if job is None:
        raise AppError(
            status_code=404,
            code="share_links.jobNotFound",
            detail=f"Job {job_id} not found.",
        )

    _check_job_ownership(job, user)

    link = await _load_active_share_link(job_id, db)
    if link is None:
        return None

    await db.refresh(link, ["created_by"])
    return _build_share_link_response(link, settings)


async def revoke_share_link(
    share_link_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> None:
    """Delete the share link row, immediately invalidating the public token.

    Args:
        share_link_id: UUID of the share link to revoke.
        user: The authenticated user performing the revocation.
        db: Active async database session.

    Raises:
        AppError 404: Share link not found.
        AppError 403: Caller does not own the linked job (non-admin).
    """
    result = await db.execute(
        select(ShareLink).where(ShareLink.id == share_link_id)
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise AppError(
            status_code=404,
            code="share_links.notFound",
            detail="Share link not found.",
        )

    # Load the parent job to enforce ownership.
    job_result = await db.execute(select(Job).where(Job.id == link.job_id))
    job = job_result.scalar_one_or_none()
    # The job must exist (CASCADE delete would have removed the link row
    # already if it were gone), but guard defensively.
    if job is None:
        raise AppError(
            status_code=404,
            code="share_links.jobNotFound",
            detail="Parent job not found.",
        )

    _check_job_ownership(job, user)

    logger.info(
        "Revoking share link: token=%s job_id=%s",
        link.token,
        link.job_id,
    )
    await db.delete(link)
    await db.commit()


async def list_share_links_for_patient(
    patient_id: uuid.UUID,
    db: AsyncSession,
    settings: Settings,
) -> list[ShareLinkResponse]:
    """Return all share links (active and expired) for jobs belonging to a patient.

    Results are ordered by creation time, newest first, so the most recently
    issued link appears at the top of the patient detail page.

    Args:
        patient_id: UUID of the patient.
        db: Active async database session.
        settings: Application settings (provides ``FRONTEND_URL``).

    Returns:
        List of ``ShareLinkResponse`` objects (may be empty).
    """
    result = await db.execute(
        select(ShareLink)
        .join(Job, Job.id == ShareLink.job_id)
        .where(Job.patient_id == patient_id)
        # Eagerly load the creator so _build_share_link_response can read
        # the username without requiring lazy-load after session close.
        .options(selectinload(ShareLink.created_by))
        .order_by(ShareLink.created_at.desc())
    )
    links = result.scalars().all()
    return [_build_share_link_response(link, settings) for link in links]


# ==============================================================================
# Public (unauthenticated) operations
# ==============================================================================


def _validate_token(link: ShareLink | None, token: str) -> ShareLink:
    """Assert that ``link`` exists and is not expired, raising the appropriate error.

    Called by all public endpoints before any further processing so the
    validation logic is not duplicated across handlers.

    Args:
        link: The ``ShareLink`` ORM instance loaded from the database, or
            ``None`` if no matching row was found.
        token: The raw token string, used only for log messages (never PII).

    Returns:
        The validated ``ShareLink`` instance.

    Raises:
        HTTPException 404: Token not found or has been revoked.
        HTTPException 410: Token exists but has expired.
    """
    if link is None:
        logger.info("Public access: token not found token=%s", token)
        raise HTTPException(
            status_code=404,
            detail="Link not found or has been revoked",
        )

    if link.expires_at is not None:
        # Normalise to UTC for comparison regardless of how the DB driver
        # returns the timestamp.
        expires_utc = link.expires_at.replace(tzinfo=timezone.utc)
        if expires_utc < datetime.now(tz=timezone.utc):
            logger.info(
                "Public access: expired token token=%s job_id=%s",
                token,
                link.job_id,
            )
            raise HTTPException(
                status_code=410,
                detail={"detail": "This link has expired", "expired": True},
            )

    return link


async def get_public_result(token: str, db: AsyncSession) -> SharedResultResponse:
    """Return the shared result payload for an unauthenticated public viewer.

    Validates the token, checks for expiry, then loads the job and its
    image results together with the linked patient record.  The patient
    query intentionally does NOT filter ``deleted_at IS NULL`` so that
    soft-deleted patients still appear by name on previously issued links.

    Args:
        token: The public share token from the URL path.
        db: Active async database session.

    Returns:
        A ``SharedResultResponse`` with patient name, scan date, and images.

    Raises:
        HTTPException 404: Token not found or revoked.
        HTTPException 410: Token expired.
    """
    link_result = await db.execute(
        select(ShareLink).where(ShareLink.token == token)
    )
    link = _validate_token(link_result.scalar_one_or_none(), token)

    logger.info(
        "Public access: result view token=%s job_id=%s",
        token,
        link.job_id,
    )

    # Load the job with its image results in a single query to avoid N+1.
    job_result = await db.execute(
        select(Job)
        .where(Job.id == link.job_id)
        .options(selectinload(Job.image_results))
    )
    job = job_result.scalar_one()

    # Load patient if the job has one.  Skip the deleted_at filter so that
    # historical links remain meaningful after a patient is soft-deleted.
    patient_name: str | None = None
    if job.patient_id is not None:
        patient_result = await db.execute(
            select(Patient).where(Patient.id == job.patient_id)
        )
        patient = patient_result.scalar_one_or_none()
        if patient is not None:
            patient_name = patient.full_name

    images = [
        SharedImageResult(
            id=ir.id,
            original_filename=ir.original_filename,
            original_size=ir.original_size,
            bounding_boxes=ir.bounding_boxes,
            is_ready=ir.mask_path is not None,
        )
        for ir in job.image_results
    ]

    return SharedResultResponse(
        patient_name=patient_name,
        scan_date=job.created_at,
        images=images,
    )


async def get_public_image_result(
    token: str,
    image_result_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[ShareLink, ImageResult]:
    """Validate a token and return the matching image result for file serving.

    Performs two security checks before returning:
    1. Token must exist and not be expired.
    2. The requested image result must belong to the token's job (prevents
       cross-job image access by an attacker who guesses image UUIDs).

    Args:
        token: The public share token from the URL path.
        image_result_id: UUID of the ``ImageResult`` row to serve.
        db: Active async database session.

    Returns:
        ``(share_link, image_result)`` tuple ready for path resolution.

    Raises:
        HTTPException 404: Token invalid/revoked, or image not found.
        HTTPException 410: Token expired.
        HTTPException 403: Image does not belong to the token's job.
    """
    link_result = await db.execute(
        select(ShareLink).where(ShareLink.token == token)
    )
    link = _validate_token(link_result.scalar_one_or_none(), token)

    image_result_row = await db.execute(
        select(ImageResult).where(ImageResult.id == image_result_id)
    )
    image_result = image_result_row.scalar_one_or_none()
    if image_result is None:
        raise HTTPException(status_code=404, detail="Image result not found.")

    # Prevent accessing images from other jobs via a valid token.
    if image_result.job_id != link.job_id:
        logger.warning(
            "Public file access: image job mismatch token=%s "
            "image_result_id=%s image_job_id=%s link_job_id=%s",
            token,
            image_result_id,
            image_result.job_id,
            link.job_id,
        )
        raise HTTPException(
            status_code=403,
            detail="Image does not belong to this share link.",
        )

    logger.info(
        "Public file access: image_result_id=%s job_id=%s",
        image_result_id,
        link.job_id,
    )
    return link, image_result
