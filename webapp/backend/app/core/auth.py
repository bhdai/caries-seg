"""FastAPI auth plumbing: cookie management and request-to-User dependencies.

This module bridges the HTTP layer and the database.  It provides:

- ``set_auth_cookie`` / ``clear_auth_cookie`` — write and delete the httponly
  JWT cookie on a Response object.
- ``get_current_user`` — FastAPI Depends() that extracts and validates the
  cookie, then loads and returns the User from the database.
- ``require_admin`` — FastAPI Depends() that delegates to ``get_current_user``
  then enforces the admin role.

No business logic lives here; route handlers receive a fully-loaded User
and can proceed without touching JWT or cookie mechanics directly.
"""

from __future__ import annotations

import uuid

import jwt
from fastapi import Depends, HTTPException, Request, status

from app.core.exceptions import AppError
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User

# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------

_COOKIE_KEY = "access_token"


def set_auth_cookie(response: Response, token: str, settings: Settings) -> None:
    """Write the JWT as an httponly ``SameSite=Lax`` cookie on *response*.

    All attributes that affect cookie identity (path, domain, secure,
    samesite) are set here.  ``clear_auth_cookie`` uses identical values so
    the browser actually removes the cookie rather than creating a second,
    conflicting one.
    """
    # Build kwargs conditionally — omitting ``domain`` when it is None avoids
    # sending ``Domain=None`` which some browsers treat as a literal string.
    kwargs: dict = dict(
        key=_COOKIE_KEY,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=settings.JWT_EXPIRY_HOURS * 3600,
        path="/",
    )
    if settings.COOKIE_DOMAIN is not None:
        kwargs["domain"] = settings.COOKIE_DOMAIN

    response.set_cookie(**kwargs)


def clear_auth_cookie(response: Response, settings: Settings) -> None:
    """Delete the auth cookie from *response*.

    Uses ``max_age=0`` with an empty value.  All other cookie attributes
    must match those used in ``set_auth_cookie`` or the browser will not
    recognise the two cookies as the same and will not remove it.
    """
    kwargs: dict = dict(
        key=_COOKIE_KEY,
        value="",
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=0,
        path="/",
    )
    if settings.COOKIE_DOMAIN is not None:
        kwargs["domain"] = settings.COOKIE_DOMAIN

    response.set_cookie(**kwargs)


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """FastAPI dependency: extract the JWT cookie and return the User.

    Steps:
    1. Read the ``access_token`` cookie — 401 if absent.
    2. Decode and validate the JWT — 401 on any jwt error (expired, tampered, …).
    3. Parse the ``sub`` claim as a UUID — 401 if malformed.
    4. Load the User from the database — 401 if the user no longer exists.
    5. Return the User ORM instance to the handler.

    The returned User is injected into handlers via ``Depends(get_current_user)``.
    """
    _401 = AppError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="auth.notAuthenticated",
        detail="Not authenticated",
    )

    # Step 1 — cookie must be present.
    token = request.cookies.get(_COOKIE_KEY)
    if not token:
        raise _401

    # Step 2 — JWT must be valid and not expired.
    try:
        payload = decode_access_token(token, settings)
    except jwt.InvalidTokenError:
        # Covers both ExpiredSignatureError and all other jwt errors so that
        # every flavour of bad token returns the same 401 (no enumeration).
        raise _401

    # Step 3 — sub must be a valid UUID.
    sub = payload.get("sub")
    try:
        user_id = uuid.UUID(str(sub))
    except (TypeError, ValueError):
        raise _401

    # Step 4 — user must still exist in the database.
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise _401

    return user


async def require_admin(
    user: User = Depends(get_current_user),
) -> User:
    """FastAPI dependency: enforce admin role.

    Delegates to ``get_current_user`` (which handles authentication), then
    checks ``user.role == "admin"``.  Raises 403 if the user is not an admin.
    Returns the User on success.
    """
    if user.role != "admin":
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="auth.adminRequired",
            detail="Admin access required",
        )
    return user
