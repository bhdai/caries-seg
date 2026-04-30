"""Route handlers for admin user-management endpoints.

All routes in this module require the ``require_admin`` dependency, which is
applied at the router level so individual handlers do not need to repeat it.

Endpoints
---------
POST   /api/admin/users              Create a new user account.
GET    /api/admin/users              List all users (paginated).
PATCH  /api/admin/users/{user_id}    Update role and/or reset password.
DELETE /api/admin/users/{user_id}    Delete a user account.

Design note: the ``require_admin`` dependency is intentionally placed on the
``APIRouter`` constructor so that adding new endpoints to this module is
safe by default — a developer cannot accidentally forget to add auth.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_admin
from app.core.database import get_db
from app.models.user import User
from app.schemas.user import (
    AdminUserResponse,
    CreateUserRequest,
    UpdateUserRequest,
    UserListResponse,
)
from app.services.users import (
    create_user,
    delete_user,
    list_users,
    update_user,
    _build_admin_response,
)

# The ``require_admin`` dependency is applied to every route in this router.
# Route handlers receive the admin user via ``Depends(require_admin)`` if they
# need to enforce self-action guards in the service layer; the dependency is
# also wired at the router level so unauthenticated and non-admin callers are
# rejected before any handler logic runs.
router = APIRouter(
    prefix="/admin/users",
    dependencies=[Depends(require_admin)],
)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AdminUserResponse)
async def create_user_route(
    body: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminUserResponse:
    """Provision a new user account with a temporary password.

    The new account always starts with ``must_change_pw=True`` so the user
    is forced to change the admin-assigned password on first login.

    Returns 409 if the username is already taken.
    """
    user = await create_user(body, db)
    return _build_admin_response(user)


@router.get("", response_model=UserListResponse)
async def list_users_route(
    page: int = Query(1, ge=1, description="1-based page number"),
    page_size: int = Query(20, ge=1, le=100, description="Records per page"),
    db: AsyncSession = Depends(get_db),
    # require_admin is already a router-level dependency; injecting it here
    # additionally gives us the admin User instance for any future use, but
    # more importantly documents that this endpoint requires admin access.
    _admin: User = Depends(require_admin),
) -> UserListResponse:
    """Return a paginated list of all users.

    Each item includes derived fields (``has_password``, ``oauth_providers``)
    so the admin UI can display account type without further requests.
    """
    return await list_users(page, page_size, db)


@router.patch("/{user_id}", response_model=AdminUserResponse)
async def update_user_route(
    user_id: uuid.UUID,
    body: UpdateUserRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminUserResponse:
    """Update a user's role and/or reset their password.

    When ``new_password`` is supplied the account's ``must_change_pw`` flag is
    reset to ``True`` so the user must choose a new password on next login.

    Returns 404 if the user does not exist.
    Returns 400 if the admin attempts to change their own role (lockout guard).
    """
    user = await update_user(user_id, body, admin, db)
    return _build_admin_response(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_route(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> None:
    """Delete a user account.

    Jobs owned by the deleted user are orphaned (``owner_id`` set to NULL)
    rather than deleted — diagnostic data is never destroyed.

    Returns 400 if the admin attempts to delete themselves.
    Returns 404 if the user does not exist.
    """
    await delete_user(user_id, admin, db)
