"""Service layer for admin user-management operations.

All database mutations for the ``/api/admin/users`` resource live here so
that route handlers remain thin HTTP-boundary translators.  Each function
receives an active ``AsyncSession`` and returns plain ORM objects or raises
``HTTPException`` on domain errors.

Design decisions
----------------
- ``create_user`` always sets ``must_change_pw=True`` so admin-provisioned
  accounts are forced to choose a new password on first login (D9).
- ``delete_user`` raises 400 rather than 404 when the requester tries to
  delete themselves to make the self-deletion guard a distinct, actionable
  error message in the admin UI.
- ``update_user`` raises 400 rather than 403 for the self-demotion guard for
  the same reason — it is a validation error, not an authorisation one.
"""

from __future__ import annotations

import math
import uuid

from fastapi import HTTPException, status

from app.core.exceptions import AppError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import (
    AdminUserResponse,
    CreateUserRequest,
    UpdateUserRequest,
    UserListResponse,
)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _build_admin_response(user: User) -> AdminUserResponse:
    """Convert a User ORM instance to ``AdminUserResponse``.

    ``AdminUserResponse`` contains two derived fields that cannot be computed
    by Pydantic's ``from_attributes`` alone:

    - ``has_password``: True when a bcrypt hash is stored (non-OAuth users).
    - ``oauth_providers``: The list of provider names from the eagerly-loaded
      ``oauth_accounts`` relationship.

    The ``oauth_accounts`` relationship is loaded with ``lazy="selectin"`` on
    the User model, so it is always populated inside an async session context.
    """
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        must_change_pw=user.must_change_pw,
        has_password=user.password_hash is not None,
        oauth_providers=[oa.provider for oa in user.oauth_accounts],
        created_at=user.created_at,
    )


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


async def create_user(body: CreateUserRequest, db: AsyncSession) -> User:
    """Create a new user account with a hashed temporary password.

    The new account starts with ``must_change_pw=True`` so the user is
    prompted to change the admin-assigned password on first login.

    Raises:
        HTTPException 409: Username already taken.
    """
    # Reject duplicate usernames up-front with a clear error rather than
    # letting the unique-constraint violation bubble up as a 500.
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none() is not None:
        raise AppError(
            status_code=status.HTTP_409_CONFLICT,
            code="users.usernameExists",
            detail="Username already exists",
        )

    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        role=body.role,
        # Always force a password change so admins cannot assign a permanent
        # password on behalf of a user without their knowledge.
        must_change_pw=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def list_users(page: int, page_size: int, db: AsyncSession) -> UserListResponse:
    """Return a paginated list of all users with their OAuth provider info.

    Args:
        page: 1-based page number.
        page_size: Number of records per page.
        db: Active async session.

    Returns:
        ``UserListResponse`` with the ``items`` slice, ``total`` count, and
        the echo of ``page`` / ``page_size`` for cursor rendering.
    """
    # Count total users for pagination metadata.
    count_result = await db.execute(select(func.count()).select_from(User))
    total = count_result.scalar_one()

    # Fetch the requested page ordered by creation date (oldest first) so
    # the list is stable across multiple admin sessions.
    offset = (page - 1) * page_size
    rows = await db.execute(
        select(User).order_by(User.created_at.asc()).offset(offset).limit(page_size)
    )
    users = rows.scalars().all()

    return UserListResponse(
        items=[_build_admin_response(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


async def update_user(
    user_id: uuid.UUID,
    body: UpdateUserRequest,
    requesting_user: User,
    db: AsyncSession,
) -> User:
    """Update role and/or reset the password for the given user.

    The ``requesting_user`` is passed in so that the service layer can enforce
    the self-demotion guard without the route handler needing to duplicate
    the check.

    Raises:
        HTTPException 404: User not found.
        HTTPException 400: Admin attempts to demote or reset their own account
                           (would risk locking out the only admin).
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="users.notFound",
            detail="User not found",
        )

    # Prevent an admin from demoting themselves — this would lock out the
    # account from admin endpoints, which is very hard to recover from in a
    # single-admin deployment.
    if user.id == requesting_user.id:
        if body.role is not None and body.role != requesting_user.role:
            raise AppError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="users.selfRoleChange",
                detail="Cannot change your own role",
            )

    if body.role is not None:
        user.role = body.role

    if body.new_password is not None:
        user.password_hash = hash_password(body.new_password)
        # When an admin resets someone's password the account must change it
        # again on next login, matching the provisioning flow.
        user.must_change_pw = True

    await db.commit()
    await db.refresh(user)
    return user


async def delete_user(
    user_id: uuid.UUID,
    requesting_user: User,
    db: AsyncSession,
) -> None:
    """Delete a user account.

    Jobs owned by the deleted user are orphaned via the ``ON DELETE SET NULL``
    foreign key constraint — diagnostic data is never destroyed (D4).

    Raises:
        HTTPException 400: Admin attempts to delete themselves.
        HTTPException 404: User not found.
    """
    # Self-deletion guard first so the error message is unambiguous — if the
    # admin's account happened to not exist this path would still be 400, which
    # is the correct signal ("you cannot do this" vs. "target not found").
    if user_id == requesting_user.id:
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            code="users.selfDelete",
            detail="Cannot delete your own account",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await db.delete(user)
    await db.commit()
