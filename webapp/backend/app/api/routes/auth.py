"""Route handlers for authentication endpoints.

Endpoints
---------
POST   /api/auth/login              Validate credentials, set httponly cookie.
POST   /api/auth/logout             Clear the auth cookie.
GET    /api/auth/me                 Return the current user (auth-state probe).
POST   /api/auth/change-password    Validate old password, set new password.
GET    /api/auth/google             Redirect to Google's OAuth2 consent screen.
GET    /api/auth/google/callback    Exchange code, set cookie, redirect to app.
POST   /api/auth/link-google        Link the current user's account to Google.

POST /api/auth/link-google is implemented in Phase 2 Step 2.3 and is not
present here yet.

This router has **no** auth dependency at the router level so that unauthenticated
callers can reach ``/login`` and ``/me`` (which returns 401 on its own when the
cookie is absent).  ``/change-password`` applies ``get_current_user`` at the
handler level because it needs the authenticated user.
"""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx
import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import clear_auth_cookie, get_current_user, set_auth_cookie
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.oauth_account import OAuthAccount
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    LinkGoogleRequest,
    LoginRequest,
    UserResponse,
)

# ---------------------------------------------------------------------------
# Google OAuth2 constants
# ---------------------------------------------------------------------------
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
# Lifetime of the CSRF state cookie in seconds.  Long enough to survive a
# slow browser redirect round-trip; short enough to not accumulate stale
# cookies in testing.
_STATE_COOKIE_MAX_AGE = 600  # 10 minutes

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


# ===========================================================================
# Google OAuth2 — Phase 2
# ===========================================================================


@router.get("/google")
async def google_login(
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Redirect the browser to Google's OAuth2 consent screen.

    If Google OAuth is not configured (GOOGLE_CLIENT_ID is None) this endpoint
    returns 404 so that deployments without Google credentials are unaffected.

    A random ``state`` token is stored in a short-lived httponly cookie to
    prevent CSRF attacks on the callback endpoint.
    """
    if settings.GOOGLE_CLIENT_ID is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Google OAuth not configured",
        )

    state = secrets.token_urlsafe(32)

    # Build the authorization URL that Google expects.  ``response_type=code``
    # requests an authorisation code which is exchanged for tokens server-side,
    # keeping secrets out of the browser URL fragment.
    params = urlencode(
        {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid profile email",
            "state": state,
        }
    )
    auth_url = f"{_GOOGLE_AUTH_URL}?{params}"

    response = RedirectResponse(url=auth_url)
    # Store the state value so the callback can verify it.  httponly prevents
    # JS from reading it; SameSite=Lax is sufficient (same origin redirect).
    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        samesite="lax",
        secure=settings.COOKIE_SECURE,
        max_age=_STATE_COOKIE_MAX_AGE,
        path="/",
    )
    return response


@router.get("/google/callback")
async def google_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Handle Google's redirect after the user grants (or denies) consent.

    Steps:
    1. If Google returned an error (user denied consent), redirect with error.
    2. Validate the CSRF state cookie against the ``state`` query param.
    3. Exchange the authorisation code for tokens via Google's token endpoint.
    4. Decode the ``id_token`` to extract the ``sub`` (Google account ID).
    5. Look up the matching ``oauth_accounts`` row.
    6. If found, issue a JWT cookie and redirect to ``/``.
    7. If not found, redirect to ``/login?error=google_not_linked``.
    """
    if settings.GOOGLE_CLIENT_ID is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Google OAuth not configured",
        )

    # Step 1 — user denied consent or Google reported an error.
    if error is not None:
        return RedirectResponse(url="/login?error=google_denied")

    # Step 2 — CSRF: validate the state cookie.
    stored_state = request.cookies.get("oauth_state")
    if not stored_state or stored_state != state:
        return RedirectResponse(url="/login?error=invalid_state")

    if code is None:
        # Should not happen if error is None and state is valid, but guard
        # defensively to avoid a confusing 422 from the missing parameter.
        return RedirectResponse(url="/login?error=invalid_state")

    # Step 3 — exchange the authorisation code for an id_token.
    try:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
                timeout=10.0,
            )
        token_response.raise_for_status()
        token_data = token_response.json()
    except httpx.HTTPError:
        # Google token exchange failed (network issue or invalid code).
        return RedirectResponse(url="/login?error=google_denied")

    id_token_str = token_data.get("id_token")
    if not id_token_str:
        return RedirectResponse(url="/login?error=google_denied")

    # Step 4 — decode the id_token without signature verification.
    #
    # The token was received directly from Google's token endpoint over HTTPS
    # (not from the browser), so the transport is already authenticated.
    # Full signature verification would require fetching Google's JWKS; that
    # is an acceptable enhancement for a future hardening pass but is outside
    # the scope of this phase.
    try:
        payload = pyjwt.decode(
            id_token_str,
            options={"verify_signature": False},
            algorithms=["RS256"],
        )
    except pyjwt.PyJWTError:
        return RedirectResponse(url="/login?error=google_denied")

    google_sub = payload.get("sub")
    if not google_sub:
        return RedirectResponse(url="/login?error=google_denied")

    # Step 5 — look up the oauth_accounts row for this Google identity.
    result = await db.execute(
        select(OAuthAccount).where(
            OAuthAccount.provider == "google",
            OAuthAccount.provider_account_id == google_sub,
        )
    )
    oauth_account = result.scalar_one_or_none()

    # Step 6 / 7 — redirect based on whether the account is linked.
    if oauth_account is None:
        # The Google account exists but has not been linked to any local user.
        # Consistent with the admin-provisioned security model (D11): no
        # auto-registration.
        return RedirectResponse(url="/login?error=google_not_linked")

    # Load the linked user and issue a session cookie.
    user = await db.get(User, oauth_account.user_id)
    if user is None:
        # The linked user was deleted while the oauth_accounts row was kept
        # (should not happen with CASCADE, but guard defensively).
        return RedirectResponse(url="/login?error=google_not_linked")

    token = create_access_token({"sub": str(user.id)}, settings)
    response = RedirectResponse(url="/")
    set_auth_cookie(response, token, settings)
    # Clear the state cookie — it is single-use.
    response.delete_cookie(key="oauth_state", path="/")
    return response


@router.post("/link-google")
async def link_google(
    body: LinkGoogleRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Link the authenticated user's account to a Google identity.

    The frontend obtains a Google authorisation ``code`` via a popup-based
    OAuth2 flow (the user authenticates with Google in a popup window and the
    code is posted back via ``postMessage``).  This endpoint exchanges the
    code for an id_token, extracts the Google ``sub``, and creates an
    ``OAuthAccount`` row binding that identity to the current user.

    Raises 404 if Google OAuth is not configured.
    Raises 409 if the Google account is already linked to a *different* user.
    Raises 400 if the code exchange fails or the id_token is invalid.
    """
    if settings.GOOGLE_CLIENT_ID is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Google OAuth not configured",
        )

    # Exchange the authorisation code for an id_token using the redirect_uri
    # provided by the caller (must match the one registered in Google Console).
    try:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "code": body.code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": body.redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
                timeout=10.0,
            )
        token_response.raise_for_status()
        token_data = token_response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google token exchange failed",
        ) from exc

    id_token_str = token_data.get("id_token")
    if not id_token_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google token exchange did not return an id_token",
        )

    # Decode the id_token to extract the Google account identifier (sub).
    # Signature verification is skipped because the token arrived directly
    # from Google's token endpoint over HTTPS (not from the browser).
    try:
        payload = pyjwt.decode(
            id_token_str,
            options={"verify_signature": False},
            algorithms=["RS256"],
        )
    except pyjwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid id_token from Google",
        ) from exc

    google_sub = payload.get("sub")
    if not google_sub:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="id_token missing sub claim",
        )

    # Check whether this Google identity is already linked to any account.
    result = await db.execute(
        select(OAuthAccount).where(
            OAuthAccount.provider == "google",
            OAuthAccount.provider_account_id == google_sub,
        )
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        if existing.user_id == user.id:
            # Already linked to this same user — idempotent success.
            return {"message": "Google account already linked"}
        # Linked to a *different* user — reject to prevent account takeover.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This Google account is already linked to another user",
        )

    # Create the new link.
    oauth_account = OAuthAccount(
        user_id=user.id,
        provider="google",
        provider_account_id=google_sub,
    )
    db.add(oauth_account)
    await db.commit()

    return {"message": "Google account linked successfully"}
