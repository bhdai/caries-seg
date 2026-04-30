"""Stateless cryptographic utilities for password hashing and JWT handling.

This module has no dependencies on database sessions, HTTP request/response
objects, or FastAPI internals.  It is a pure utility layer that the auth
dependencies (``app/core/auth.py``) and route handlers call into.

Keeping I/O concerns out of here makes every function trivially unit-testable
without any mocking.

Note: the plan specifies ``passlib[bcrypt]`` as the hashing backend, but
passlib 1.7.4 is incompatible with bcrypt ≥ 4.0 (its internal
``detect_wrap_bug`` helper fails with ``ValueError: password cannot be longer
than 72 bytes``).  We use the ``bcrypt`` package directly instead; the
public API surface is identical.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import Settings


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    """Hash a plaintext password using bcrypt.

    Returns the bcrypt hash string suitable for storing in
    ``users.password_hash``.
    """
    # bcrypt.hashpw requires bytes; encode the plaintext to UTF-8 first.
    # bcrypt silently truncates passwords longer than 72 bytes — this is an
    # inherent bcrypt property.  If we ever need to support longer passwords
    # we would pre-hash with SHA-256 before bcrypt (bcrypt-sha256 pattern).
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash.

    Uses bcrypt's built-in constant-time comparison so the check is
    resistant to timing attacks.  Returns ``True`` if the password matches,
    ``False`` otherwise.
    """
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# JWT encode / decode
# ---------------------------------------------------------------------------


def create_access_token(data: dict[str, Any], settings: Settings) -> str:
    """Encode a signed JWT from the given payload dict.

    The caller is responsible for populating ``data`` with at minimum
    ``{"sub": str(user.id)}``.  This function appends the standard ``exp``
    (expiry) and ``iat`` (issued-at) claims before signing.

    The token is signed with ``settings.JWT_SECRET`` using
    ``settings.JWT_ALGORITHM`` (default HS256).
    """
    now = datetime.now(UTC)
    payload = {
        **data,
        "iat": now,
        "exp": now + timedelta(hours=settings.JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    """Decode and validate a JWT string.

    Returns the full payload dict on success.

    Raises:
        jwt.ExpiredSignatureError: The token's ``exp`` claim is in the past.
        jwt.InvalidTokenError:     Any other validation failure (bad signature,
                                   malformed token, algorithm mismatch, etc.).

    Callers in ``app/core/auth.py`` catch these exceptions and convert them
    to HTTP 401 responses.
    """
    return jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
    )
