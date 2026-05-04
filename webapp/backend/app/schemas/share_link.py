"""Pydantic schemas for ShareLink request and response payloads.

Phase 1 only defines the response schema so that ``PatientDetailResponse``
can reference it.  The create/revoke/public-access endpoints are
implemented in Phase 2.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateShareLinkRequest(BaseModel):
    """Validated body for ``POST /api/share-links``."""

    job_id: uuid.UUID
    # Number of days until the link expires.  None means no expiry.
    # Allowed values: 7, 30, 90, or None.
    expires_in_days: int | None = 30


class ShareLinkResponse(BaseModel):
    """Full share link payload returned by create and list endpoints.

    ``url`` is a computed field constructed from the frontend base URL and
    the token.  ``is_expired`` is also computed so clients don't need to
    do their own timestamp arithmetic.
    """

    id: uuid.UUID
    job_id: uuid.UUID
    token: str
    # Fully-qualified URL the patient opens: {FRONTEND_URL}/shared/{token}.
    url: str
    expires_at: datetime | None
    # True if expires_at is set and is in the past.
    is_expired: bool
    created_at: datetime
    # Username of the creating user; None if the user account was deleted.
    created_by_username: str | None

    model_config = {"from_attributes": True}
