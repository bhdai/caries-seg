"""Pydantic schemas for admin user-management request and response payloads.

Used by the admin routes (``/api/admin/users``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CreateUserRequest(BaseModel):
    """Payload for ``POST /api/admin/users``.

    Admins provision accounts with a temporary password.  The
    ``must_change_pw`` flag is set to ``True`` by the service layer so the
    new user is forced to change the password on first login.
    """

    # Restrict usernames to alphanumeric characters plus dots, hyphens, and
    # underscores — the same set accepted by most identity systems.
    username: str = Field(
        min_length=1,
        max_length=150,
        pattern=r"^[a-zA-Z0-9._-]+$",
    )
    password: str = Field(min_length=8, max_length=128)
    role: Literal["user", "admin"] = "user"


class UpdateUserRequest(BaseModel):
    """Payload for ``PATCH /api/admin/users/{id}``.

    Both fields are optional so the caller can update only what is needed
    without re-supplying the unchanged field.
    """

    role: Literal["user", "admin"] | None = None
    new_password: str | None = Field(None, min_length=8, max_length=128)


class AdminUserResponse(BaseModel):
    """Full user record returned in the admin user list and update responses.

    Includes the derived ``has_password`` and ``oauth_providers`` fields so
    the admin UI can show account type at a glance.
    """

    id: uuid.UUID
    username: str
    role: str
    must_change_pw: bool
    # Derived from password_hash is not None; never exposes the hash itself.
    has_password: bool
    # E.g. ["google"] — the list of linked OAuth providers for this user.
    oauth_providers: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    """Paginated list of admin user records."""

    items: list[AdminUserResponse]
    total: int
    page: int
    page_size: int
