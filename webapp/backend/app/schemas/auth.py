"""Pydantic schemas for authentication request and response payloads.

Used by the auth routes (login, logout, me, change-password).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Credentials submitted to ``POST /api/auth/login``."""

    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1)


class ChangePasswordRequest(BaseModel):
    """Payload for ``POST /api/auth/change-password``."""

    current_password: str = Field(min_length=1)
    # Enforce a minimum of 8 characters so that admin-issued temporary
    # passwords cannot be replaced with trivially short ones.
    new_password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    """Public user representation embedded in auth responses and returned by
    ``GET /api/auth/me``.

    Only fields that the frontend needs are exposed; ``password_hash`` is
    never serialised.
    """

    id: uuid.UUID
    username: str
    role: str
    must_change_pw: bool

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    """Response body for login and change-password endpoints.

    The ``user`` field lets the frontend update its AuthContext state in the
    same round-trip that sets the cookie, avoiding a separate GET /api/auth/me
    call immediately after login.
    """

    user: UserResponse
    message: str
