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

Auth-guard tests (401 / 403 when calling protected routes without valid auth)
are also covered here to avoid duplicating them in every other test module.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

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
    assert resp.json()["detail"] == "Invalid credentials"


async def test_login_unknown_user(client: AsyncClient) -> None:
    """An unknown username returns the same generic 401."""
    resp = await client.post(
        "/api/auth/login",
        json={"username": "nobody_here", "password": "any_password"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


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
    assert resp.json()["detail"] == "Invalid credentials"


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
    """Providing the wrong current password returns 401."""
    resp = await client.post(
        "/api/auth/change-password",
        json={
            "current_password": "wrong_current_password",
            "new_password": "NewPassword2!",
        },
    )
    assert resp.status_code == 401


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


async def test_admin_create_user_requires_auth(client: AsyncClient) -> None:
    """Unauthenticated request to admin endpoint returns 401."""
    resp = await client.post(
        "/api/admin/users",
        json={"username": "should_fail", "password": "Password1!"},
    )
    assert resp.status_code == 401


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
    assert resp.status_code == 400
    assert "role" in resp.json()["detail"].lower()


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
    assert resp.status_code == 400
    assert "own account" in resp.json()["detail"].lower()


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
