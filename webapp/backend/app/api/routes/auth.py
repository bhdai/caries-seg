"""Route handlers for authentication endpoints.

Endpoints
---------
POST   /api/auth/login              Validate credentials, set httponly cookie.
POST   /api/auth/logout             Clear the auth cookie.
GET    /api/auth/me                 Return the current user (auth-state probe).
POST   /api/auth/change-password    Validate old password, set new password.

Google OAuth endpoints (GET /api/auth/google, GET /api/auth/google/callback,
POST /api/auth/link-google) are implemented in Phase 2 and are not present here.

This router has **no** auth dependency at the router level so that unauthenticated
callers can reach ``/login`` and ``/me`` (which returns 401 on its own when the
cookie is absent).  ``/change-password`` applies ``get_current_user`` at the
handler level because it needs the authenticated user.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import clear_auth_cookie, get_current_user, set_auth_cookie
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth")


@router.post("/login")
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Validate credentials and issue an httponly JWT cookie.

    All three failure modes (unknown username, no password set, wrong
    password) return the same 401 with the same message to prevent username
    enumeration.
    """
    _invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
    )

    # Load user by username — fail generically so callers cannot probe for
    # existing usernames via timing or error-message differences.
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()
    if user is None:
        raise _invalid

    # OAuth-only accounts have no local password; treat as invalid credentials
    # rather than exposing that the account exists without a password.
    if user.password_hash is None:
        raise _invalid

    if not verify_password(body.password, user.password_hash):
        raise _invalid

    token = create_access_token({"sub": str(user.id)}, settings)

    # Build the response body first, then attach the cookie so that the
    # JSONResponse constructor receives a plain dict rather than a Response.
    response_body = AuthResponse(
        user=UserResponse.model_validate(user),
        message="Logged in",
    )
    response = JSONResponse(content=response_body.model_dump(mode="json"))
    set_auth_cookie(response, token, settings)
    return response


@router.post("/logout")
async def logout(
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Clear the auth cookie."""
    response = JSONResponse(content={"message": "Logged out"})
    clear_auth_cookie(response, settings)
    return response


@router.get("/me", response_model=UserResponse)
async def me(
    user: User = Depends(get_current_user),
) -> UserResponse:
    """Return the current user's public profile.

    This is the frontend's single source of truth for authentication state on
    page load.  A 401 response means the cookie is absent or expired.
    """
    return UserResponse.model_validate(user)


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Validate the current password and set a new one.

    Also clears ``must_change_pw`` so the frontend allows access to the rest
    of the application after a forced first-login password change.

    A new JWT cookie is issued so the session lifetime resets — the user does
    not need to log in again after changing their password.
    """
    if user.password_hash is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account has no password",
        )

    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password incorrect",
        )

    # Re-fetch by PK so mutations happen on an object that belongs to
    # this session (the dep-override in tests may inject a user from a
    # different session, which would make db.refresh() fail).
    db_user = await db.get(User, user.id)
    assert db_user is not None, "authenticated user must exist in the database"
    db_user.password_hash = hash_password(body.new_password)
    db_user.must_change_pw = False
    await db.commit()
    # Re-query to pick up the server-side updated_at refresh.
    await db.refresh(db_user)

    token = create_access_token({"sub": str(db_user.id)}, settings)
    response_body = AuthResponse(
        user=UserResponse.model_validate(db_user),
        message="Password changed",
    )
    response = JSONResponse(content=response_body.model_dump(mode="json"))
    set_auth_cookie(response, token, settings)
    return response
