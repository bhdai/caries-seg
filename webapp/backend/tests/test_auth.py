"""Integration tests for Phase 1 auth endpoints.

Covered endpoints:
  POST /api/auth/login              — credential validation, cookie issuance
  POST /api/auth/logout             — cookie clearing
  GET  /api/auth/me                 — auth-state probe
  POST /api/auth/change-password    — password rotation

  POST   /api/admin/users           — admin: create user
  GET    /api/admin/users           — admin: list users
  PATCH  /api/admin/users/{id}      — admin: update role / reset password
  DELETE /api/admin/users/{id}      — admin: delete user

  GET  /api/auth/google             — redirect to Google consent screen
  GET  /api/auth/google/callback    — exchange code, set cookie or error redirect
  POST /api/auth/link-google        — link current user to Google identity

Auth-guard tests (401 / 403 when calling protected routes without valid auth)
are also covered here to avoid duplicating them in every other test module.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import jwt as pyjwt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from tests.conftest import _TEST_ADMIN_PASSWORD, _TEST_USER_PASSWORD

pytestmark = pytest.mark.asyncio


# ===========================================================================
# POST /api/auth/login
# ===========================================================================


async def test_login_success(client: AsyncClient, test_user) -> None:
    """Valid credentials return 200, user body, and an httponly access_token cookie."""
    resp = await client.post(
        "/api/auth/login",
        json={"username": test_user.username, "password": _TEST_USER_PASSWORD},
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["message"] == "Logged in"
    assert body["user"]["username"] == test_user.username
    assert body["user"]["role"] == "user"
    assert "must_change_pw" in body["user"]

    # The httponly cookie must be present so subsequent requests are
    # authenticated without JS-readable storage (Decision D2).
    assert "access_token" in resp.cookies


async def test_login_wrong_password(client: AsyncClient, test_user) -> None:
    """A wrong password returns the same generic 401 as an unknown username.

    All three failure modes (bad username, no password set, wrong password)
    must return identical responses to prevent username enumeration.
    """
    resp = await client.post(
        "/api/auth/login",
        json={"username": test_user.username, "password": "wrong_password"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["detail"] == "Invalid credentials"
    assert "code" in body
    assert body["code"] == "auth.invalidCredentials"


async def test_login_unknown_user(client: AsyncClient) -> None:
    """An unknown username returns the same generic 401."""
    resp = await client.post(
        "/api/auth/login",
        json={"username": "nobody_here", "password": "any_password"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["detail"] == "Invalid credentials"
    assert "code" in body
    assert body["code"] == "auth.invalidCredentials"


async def test_login_oauth_only_account(
    client: AsyncClient, database_url: str
) -> None:
    """An account with no password_hash returns the same generic 401.

    OAuth-only accounts have ``password_hash=None`` and must not reveal
    that they exist by returning a different error.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.models.user import User

    # Provision an OAuth-only user (no password) directly in the DB.
    engine = create_async_engine(database_url)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        oauth_user = User(
            username="oauth_only_user",
            password_hash=None,
            role="user",
            must_change_pw=False,
        )
        session.add(oauth_user)
        await session.commit()
    await engine.dispose()

    resp = await client.post(
        "/api/auth/login",
        json={"username": "oauth_only_user", "password": "any_password"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["detail"] == "Invalid credentials"
    assert "code" in body
    assert body["code"] == "auth.invalidCredentials"


async def test_login_missing_fields(client: AsyncClient) -> None:
    """Missing required fields are rejected with 422 before business logic runs."""
    resp = await client.post("/api/auth/login", json={})
    assert resp.status_code == 422


# ===========================================================================
# POST /api/auth/logout
# ===========================================================================


async def test_logout_clears_cookie(client: AsyncClient, test_user) -> None:
    """Logout returns 200 and sets the cookie with max_age=0 to clear it."""
    # Log in first to obtain a cookie.
    login_resp = await client.post(
        "/api/auth/login",
        json={"username": test_user.username, "password": _TEST_USER_PASSWORD},
    )
    assert login_resp.status_code == 200

    # Then log out.
    logout_resp = await client.post("/api/auth/logout")
    assert logout_resp.status_code == 200
    assert logout_resp.json()["message"] == "Logged out"

    # The Set-Cookie header with max_age=0 instructs the browser to remove the
    # cookie.  httpx will have removed the cookie from its jar by now.
    assert "access_token" not in logout_resp.cookies


# ===========================================================================
# GET /api/auth/me
# ===========================================================================


async def test_me_returns_current_user(client: AsyncClient, user_override) -> None:
    """With valid auth, /me returns the authenticated user's public profile."""
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 200

    body = resp.json()
    assert body["username"] == "testuser"
    assert body["role"] == "user"
    assert "must_change_pw" in body


async def test_me_unauthenticated(client: AsyncClient) -> None:
    """Without a cookie, /me returns 401."""
    # No user_override fixture → get_current_user raises 401.
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401
    body = resp.json()
    assert "code" in body
    assert body["code"] == "auth.notAuthenticated"


# ===========================================================================
# POST /api/auth/change-password
# ===========================================================================


async def test_change_password_success(
    client: AsyncClient, user_override, test_user
) -> None:
    """Changing the password with correct old password returns 200 and a new cookie."""
    resp = await client.post(
        "/api/auth/change-password",
        json={
            "current_password": _TEST_USER_PASSWORD,
            "new_password": "NewPassword2!",
        },
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    # must_change_pw should be cleared after a successful password change.
    assert body["user"]["must_change_pw"] is False
    # A fresh access_token cookie is issued so the session stays alive.
    assert "access_token" in resp.cookies


async def test_change_password_wrong_current(
    client: AsyncClient, user_override
) -> None:
    """Providing the wrong current password returns 400."""
    resp = await client.post(
        "/api/auth/change-password",
        json={
            "current_password": "wrong_current_password",
            "new_password": "NewPassword2!",
        },
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "code" in body
    assert body["code"] == "auth.wrongPassword"


async def test_change_password_too_short(
    client: AsyncClient, user_override
) -> None:
    """A new password shorter than 8 characters is rejected by Pydantic with 422."""
    resp = await client.post(
        "/api/auth/change-password",
        json={
            "current_password": _TEST_USER_PASSWORD,
            "new_password": "short",
        },
    )
    assert resp.status_code == 422


async def test_change_password_requires_auth(client: AsyncClient) -> None:
    """Without auth, change-password returns 401."""
    resp = await client.post(
        "/api/auth/change-password",
        json={
            "current_password": _TEST_USER_PASSWORD,
            "new_password": "NewPassword2!",
        },
    )
    assert resp.status_code == 401
    body = resp.json()
    assert "code" in body
    assert body["code"] == "auth.notAuthenticated"


# ===========================================================================
# POST /api/admin/users
# ===========================================================================


async def test_admin_create_user_success(
    client: AsyncClient, admin_override
) -> None:
    """Admin can create a new user account; response includes derived fields."""
    resp = await client.post(
        "/api/admin/users",
        json={
            "username": "newstaff",
            "password": "StaffPass1!",
            "role": "user",
        },
    )
    assert resp.status_code == 201, resp.text

    body = resp.json()
    assert body["username"] == "newstaff"
    assert body["role"] == "user"
    # New accounts always start with must_change_pw=True.
    assert body["must_change_pw"] is True
    # Derived fields
    assert body["has_password"] is True
    assert body["oauth_providers"] == []


async def test_admin_create_user_duplicate_username(
    client: AsyncClient, admin_override, test_user
) -> None:
    """Creating a user with an existing username returns 409."""
    resp = await client.post(
        "/api/admin/users",
        json={
            "username": test_user.username,
            "password": "SomePass1!",
        },
    )
    assert resp.status_code == 409
    body = resp.json()
    assert "code" in body
    assert body["code"] == "users.usernameExists"


async def test_admin_create_user_invalid_username(
    client: AsyncClient, admin_override
) -> None:
    """Usernames with special characters outside the allowed set are rejected (422)."""
    resp = await client.post(
        "/api/admin/users",
        json={"username": "bad user!", "password": "Password1!"},
    )
    assert resp.status_code == 422


async def test_admin_create_user_requires_admin(
    client: AsyncClient, user_override
) -> None:
    """A regular user cannot reach admin endpoints; 403 is returned."""
    resp = await client.post(
        "/api/admin/users",
        json={"username": "should_fail", "password": "Password1!"},
    )
    assert resp.status_code == 403
    body = resp.json()
    assert "code" in body
    assert body["code"] == "auth.adminRequired"


async def test_admin_create_user_requires_auth(client: AsyncClient) -> None:
    """Unauthenticated request to admin endpoint returns 401."""
    resp = await client.post(
        "/api/admin/users",
        json={"username": "should_fail", "password": "Password1!"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert "code" in body
    assert body["code"] == "auth.notAuthenticated"


# ===========================================================================
# GET /api/admin/users
# ===========================================================================


async def test_admin_list_users_empty(client: AsyncClient, admin_override) -> None:
    """Admin list endpoint returns pagination metadata even for empty results.

    Note: ``test_admin`` itself is in the DB (created by ``admin_override``).
    """
    resp = await client.get("/api/admin/users")
    assert resp.status_code == 200

    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert body["page"] == 1
    # At least the admin fixture user should be present.
    assert body["total"] >= 1


async def test_admin_list_users_pagination(
    client: AsyncClient, admin_override
) -> None:
    """Pagination params are echoed back in the response."""
    resp = await client.get("/api/admin/users?page=1&page_size=5")
    assert resp.status_code == 200

    body = resp.json()
    assert body["page"] == 1
    assert body["page_size"] == 5


async def test_admin_list_users_includes_test_user(
    client: AsyncClient, admin_override, test_user
) -> None:
    """The list endpoint shows all users including the non-admin test user."""
    resp = await client.get("/api/admin/users")
    assert resp.status_code == 200

    usernames = {u["username"] for u in resp.json()["items"]}
    assert test_user.username in usernames


# ===========================================================================
# PATCH /api/admin/users/{user_id}
# ===========================================================================


async def test_admin_update_user_role(
    client: AsyncClient, admin_override, test_user
) -> None:
    """Admin can promote a regular user to admin."""
    resp = await client.patch(
        f"/api/admin/users/{test_user.id}",
        json={"role": "admin"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "admin"


async def test_admin_reset_user_password(
    client: AsyncClient, admin_override, test_user
) -> None:
    """Admin can reset a user's password; must_change_pw is set to True."""
    resp = await client.patch(
        f"/api/admin/users/{test_user.id}",
        json={"new_password": "ResetPass1!"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["must_change_pw"] is True


async def test_admin_cannot_demote_self(
    client: AsyncClient, admin_override, test_admin
) -> None:
    """An admin cannot change their own role — prevents accidental lockout."""
    resp = await client.patch(
        f"/api/admin/users/{test_admin.id}",
        json={"role": "user"},
    )
    assert resp.status_code == 403
    body = resp.json()
    assert "code" in body
    assert body["code"] == "users.selfRoleChange"
    assert "role" in body["detail"].lower()


async def test_admin_update_nonexistent_user(
    client: AsyncClient, admin_override
) -> None:
    """Updating a nonexistent user returns 404."""
    missing_id = uuid.uuid4()
    resp = await client.patch(
        f"/api/admin/users/{missing_id}",
        json={"role": "user"},
    )
    assert resp.status_code == 404
    body = resp.json()
    assert "code" in body
    assert body["code"] == "users.notFound"


# ===========================================================================
# DELETE /api/admin/users/{user_id}
# ===========================================================================


async def test_admin_delete_user_success(
    client: AsyncClient, admin_override, test_user
) -> None:
    """Admin can delete another user; the user no longer appears in the list."""
    del_resp = await client.delete(f"/api/admin/users/{test_user.id}")
    assert del_resp.status_code == 204

    # Verify the user is gone from the listing.
    list_resp = await client.get("/api/admin/users")
    usernames = {u["username"] for u in list_resp.json()["items"]}
    assert test_user.username not in usernames


async def test_admin_cannot_delete_self(
    client: AsyncClient, admin_override, test_admin
) -> None:
    """An admin cannot delete their own account — self-deletion guard."""
    resp = await client.delete(f"/api/admin/users/{test_admin.id}")
    assert resp.status_code == 403
    body = resp.json()
    assert "code" in body
    assert body["code"] == "users.selfDelete"
    assert "own account" in body["detail"].lower()


async def test_admin_delete_nonexistent_user(
    client: AsyncClient, admin_override
) -> None:
    """Deleting a nonexistent user returns 404."""
    missing_id = uuid.uuid4()
    resp = await client.delete(f"/api/admin/users/{missing_id}")
    assert resp.status_code == 404


# ===========================================================================
# Full login → me → logout flow
# ===========================================================================


async def test_full_login_me_logout_flow(
    client: AsyncClient, test_user
) -> None:
    """End-to-end: login, verify /me returns user, then logout clears state."""
    # 1. Login — cookie is set.
    login = await client.post(
        "/api/auth/login",
        json={"username": test_user.username, "password": _TEST_USER_PASSWORD},
    )
    assert login.status_code == 200
    assert "access_token" in login.cookies

    # 2. /me with the cookie — returns the user (httpx sends cookies automatically).
    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == test_user.username

    # 3. Logout clears the cookie.
    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 200

    # 4. /me with no valid cookie → 401.
    me_after = await client.get("/api/auth/me")
    assert me_after.status_code == 401
    me_after_body = me_after.json()
    assert "code" in me_after_body
    assert me_after_body["code"] == "auth.notAuthenticated"


# ===========================================================================
# Phase 2 — Google OAuth2
# ===========================================================================
#
# All tests that exercise the Google OAuth endpoints either:
#   a) need `google_settings` to configure GOOGLE_CLIENT_ID etc., or
#   b) test the "not configured" path and deliberately omit that fixture.
#
# httpx calls to Google's token endpoint are intercepted by patching
# `httpx.AsyncClient` inside the auth routes module so no real network
# traffic is generated.
# ===========================================================================

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_GOOGLE_CLIENT_ID = "test-google-client-id.apps.googleusercontent.com"
_GOOGLE_CLIENT_SECRET = "test-google-client-secret"
_GOOGLE_REDIRECT_URI = "http://localhost:8000/api/auth/google/callback"

# A fake Google `sub` that consistently identifies a test Google identity
# across callback and link-google tests.
_GOOGLE_SUB = "google-sub-0000001"


def _make_fake_id_token(sub: str = _GOOGLE_SUB) -> str:
    """Encode a minimal JWT that mimics a Google id_token.

    The token is signed with HS256 only so it can be created without an RSA
    key.  The callback/link-google handlers decode it with
    ``verify_signature=False`` (token is received directly from Google over
    HTTPS), so the algorithm does not matter for correctness tests.
    """
    return pyjwt.encode({"sub": sub}, "fake-secret", algorithm="HS256")


def _make_google_token_response(sub: str = _GOOGLE_SUB) -> dict:
    """Build a fake JSON body matching Google's token endpoint response."""
    return {
        "access_token": "fake-access-token",
        "id_token": _make_fake_id_token(sub),
        "token_type": "Bearer",
        "expires_in": 3600,
    }


class _FakeHttpxClient:
    """Minimal async context manager that stubs out httpx.AsyncClient.

    The ``post`` method returns a mock whose ``.json()`` yields ``json_data``
    and whose ``.raise_for_status()`` is a no-op (simulating a 200 response).

    Pass ``raise_on_post=True`` to simulate a network error.
    """

    def __init__(self, json_data: dict, raise_on_post: bool = False) -> None:
        self._json = json_data
        self._raise = raise_on_post

    async def __aenter__(self) -> "_FakeHttpxClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    async def post(self, *args: object, **kwargs: object) -> MagicMock:
        import httpx

        if self._raise:
            raise httpx.ConnectError("simulated network error")
        resp = MagicMock()
        resp.json.return_value = self._json
        resp.raise_for_status = MagicMock()
        return resp


@pytest.fixture
def google_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject Google OAuth env vars and invalidate the settings cache.

    Fixtures that need the Google OAuth routes to be active should declare
    this as a dependency.  The settings cache is cleared on teardown so
    subsequent tests start fresh.
    """
    monkeypatch.setenv("GOOGLE_CLIENT_ID", _GOOGLE_CLIENT_ID)
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", _GOOGLE_CLIENT_SECRET)
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", _GOOGLE_REDIRECT_URI)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# GET /api/auth/google
# ---------------------------------------------------------------------------


async def test_google_login_not_configured(
    client: AsyncClient,
    no_google_settings: None,
) -> None:
    """Without Google OAuth env vars, the endpoint returns 503."""
    resp = await client.get("/api/auth/google", follow_redirects=False)
    assert resp.status_code == 503
    body = resp.json()
    assert "code" in body
    assert body["code"] == "auth.oauthNotConfigured"
    assert "not configured" in body["detail"].lower()


async def test_google_login_redirects_to_google(
    client: AsyncClient, google_settings: None
) -> None:
    """With Google OAuth configured, the endpoint 302-redirects to Google."""
    resp = await client.get("/api/auth/google", follow_redirects=False)
    assert resp.status_code == 307 or resp.status_code == 302

    location = resp.headers["location"]
    assert "accounts.google.com" in location
    assert "response_type=code" in location
    assert "scope=openid" in location

    # A CSRF state cookie must be set so the callback can validate it.
    assert "oauth_state" in resp.cookies


# ---------------------------------------------------------------------------
# GET /api/auth/google/callback
# ---------------------------------------------------------------------------


async def test_google_callback_not_configured(
    client: AsyncClient,
    no_google_settings: None,
) -> None:
    """Without Google OAuth env vars, the callback endpoint returns 404."""
    resp = await client.get(
        "/api/auth/google/callback?code=x&state=y",
        follow_redirects=False,
    )
    assert resp.status_code == 404


async def test_google_callback_user_denied(
    client: AsyncClient, google_settings: None
) -> None:
    """When Google reports an error (user denied consent), redirect to /login."""
    # Seed a valid state cookie so the error short-circuits before state check.
    client.cookies.set("oauth_state", "test-state")
    resp = await client.get(
        "/api/auth/google/callback?error=access_denied&state=test-state",
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "http://localhost:5173/login?error=google_denied"


async def test_google_callback_invalid_state(
    client: AsyncClient, google_settings: None
) -> None:
    """A state mismatch (CSRF attempt) redirects to /login?error=invalid_state."""
    # Set a different state in the cookie vs the query param.
    client.cookies.set("oauth_state", "correct-state")
    resp = await client.get(
        "/api/auth/google/callback?code=abc&state=tampered-state",
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "http://localhost:5173/login?error=invalid_state"


async def test_google_callback_missing_state_cookie(
    client: AsyncClient, google_settings: None
) -> None:
    """If the state cookie is missing entirely, redirect with invalid_state."""
    # No cookie set at all.
    resp = await client.get(
        "/api/auth/google/callback?code=abc&state=any",
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "http://localhost:5173/login?error=invalid_state"


async def test_google_callback_account_not_linked(
    client: AsyncClient, google_settings: None
) -> None:
    """A valid Google login for an unregistered sub redirects to google_not_linked."""
    client.cookies.set("oauth_state", "test-state")

    fake_token_body = _make_google_token_response()
    with patch(
        "app.api.routes.auth.httpx.AsyncClient",
        return_value=_FakeHttpxClient(fake_token_body),
    ):
        resp = await client.get(
            "/api/auth/google/callback?code=valid-code&state=test-state",
            follow_redirects=False,
        )

    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "http://localhost:5173/login?error=google_not_linked"


async def test_google_callback_linked_account_logs_in(
    client: AsyncClient,
    google_settings: None,
    test_user,
    database_url: str,
) -> None:
    """A Google identity linked to a user sets the JWT cookie and redirects to /."""
    # Create the OAuthAccount row linking test_user to the fake Google sub.
    engine = create_async_engine(database_url)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        from app.models.oauth_account import OAuthAccount

        link = OAuthAccount(
            user_id=test_user.id,
            provider="google",
            provider_account_id=_GOOGLE_SUB,
        )
        session.add(link)
        await session.commit()
    await engine.dispose()

    client.cookies.set("oauth_state", "test-state")

    fake_token_body = _make_google_token_response()
    with patch(
        "app.api.routes.auth.httpx.AsyncClient",
        return_value=_FakeHttpxClient(fake_token_body),
    ):
        resp = await client.get(
            "/api/auth/google/callback?code=valid-code&state=test-state",
            follow_redirects=False,
        )

    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "http://localhost:5173/"
    # JWT cookie must be issued so the frontend can call /api/auth/me.
    assert "access_token" in resp.cookies
    # The one-time state cookie must be cleared.
    assert resp.cookies.get("oauth_state") != "test-state" or "oauth_state" not in resp.cookies


async def test_google_callback_token_exchange_failure(
    client: AsyncClient, google_settings: None
) -> None:
    """A network error during code exchange redirects to /login?error=google_denied."""
    client.cookies.set("oauth_state", "test-state")

    with patch(
        "app.api.routes.auth.httpx.AsyncClient",
        return_value=_FakeHttpxClient({}, raise_on_post=True),
    ):
        resp = await client.get(
            "/api/auth/google/callback?code=bad-code&state=test-state",
            follow_redirects=False,
        )

    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "http://localhost:5173/login?error=google_denied"


# ---------------------------------------------------------------------------
# POST /api/auth/link-google
# ---------------------------------------------------------------------------


async def test_link_google_not_configured(
    client: AsyncClient,
    user_override: None,
    no_google_settings: None,
) -> None:
    """Without Google OAuth configured, link-google returns 404."""
    resp = await client.post(
        "/api/auth/link-google",
        json={"code": "any", "state": "any-state"},
    )
    assert resp.status_code == 404


async def test_link_google_success(
    client: AsyncClient,
    google_settings: None,
    user_override,
    test_user,
    database_url: str,
) -> None:
    """Linking a new Google identity creates an OAuthAccount row."""
    from sqlalchemy import select

    from app.models.oauth_account import OAuthAccount

    fake_token_body = _make_google_token_response()
    client.cookies.set("oauth_link_state", "test-link-state")
    with patch(
        "app.api.routes.auth.httpx.AsyncClient",
        return_value=_FakeHttpxClient(fake_token_body),
    ):
        resp = await client.post(
            "/api/auth/link-google",
            json={"code": "valid-code", "state": "test-link-state"},
        )

    assert resp.status_code == 200, resp.text
    assert "linked" in resp.json()["message"].lower()

    # Verify the row was created in the database.
    engine = create_async_engine(database_url)
    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(OAuthAccount).where(
                OAuthAccount.user_id == test_user.id,
                OAuthAccount.provider == "google",
                OAuthAccount.provider_account_id == _GOOGLE_SUB,
            )
        )
        account = result.scalar_one_or_none()
    await engine.dispose()
    assert account is not None


async def test_link_google_idempotent(
    client: AsyncClient,
    google_settings: None,
    user_override,
    test_user,
    database_url: str,
) -> None:
    """Linking the same Google identity twice for the same user returns 200 (idempotent)."""
    # Pre-create the link.
    engine = create_async_engine(database_url)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        from app.models.oauth_account import OAuthAccount

        link = OAuthAccount(
            user_id=test_user.id,
            provider="google",
            provider_account_id=_GOOGLE_SUB,
        )
        session.add(link)
        await session.commit()
    await engine.dispose()

    fake_token_body = _make_google_token_response()
    client.cookies.set("oauth_link_state", "test-link-state")
    with patch(
        "app.api.routes.auth.httpx.AsyncClient",
        return_value=_FakeHttpxClient(fake_token_body),
    ):
        resp = await client.post(
            "/api/auth/link-google",
            json={"code": "any-code", "state": "test-link-state"},
        )

    assert resp.status_code == 200
    assert "already linked" in resp.json()["message"].lower()


async def test_link_google_duplicate_different_user(
    client: AsyncClient,
    google_settings: None,
    user_override,
    test_user,
    database_url: str,
) -> None:
    """409 is returned when the Google identity is already linked to a different user."""
    # Create a second user and link the Google sub to them.
    engine = create_async_engine(database_url)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        from app.core.security import hash_password
        from app.models.oauth_account import OAuthAccount
        from app.models.user import User

        other_user = User(
            username="otheruser",
            password_hash=hash_password("OtherPass1!"),
            role="user",
            must_change_pw=False,
        )
        session.add(other_user)
        await session.flush()  # populate other_user.id

        link = OAuthAccount(
            user_id=other_user.id,
            provider="google",
            provider_account_id=_GOOGLE_SUB,
        )
        session.add(link)
        await session.commit()
    await engine.dispose()

    # Now test_user (via user_override) tries to claim the same Google identity.
    fake_token_body = _make_google_token_response()
    client.cookies.set("oauth_link_state", "test-link-state")
    with patch(
        "app.api.routes.auth.httpx.AsyncClient",
        return_value=_FakeHttpxClient(fake_token_body),
    ):
        resp = await client.post(
            "/api/auth/link-google",
            json={"code": "any-code", "state": "test-link-state"},
        )

    assert resp.status_code == 409
    body = resp.json()
    assert "code" in body
    assert body["code"] == "auth.googleAlreadyLinked"
    assert "another user" in body["detail"].lower()


async def test_link_google_requires_auth(
    client: AsyncClient, google_settings: None
) -> None:
    """Without authentication, link-google returns 401."""
    resp = await client.post(
        "/api/auth/link-google",
        json={"code": "any", "redirect_uri": _GOOGLE_REDIRECT_URI},
    )
    assert resp.status_code == 401
