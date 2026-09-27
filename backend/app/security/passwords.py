"""Password hashing helpers.

Passwords are hashed with Argon2. Plaintext passwords must never be stored
or logged.
"""

from __future__ import annotations

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
)

_uncached_dummy_hash: str | None = None


def hash_password(password: str) -> str:
    """Hash a plaintext password for storage."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return whether a password matches an Argon2 password hash."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def burn_password_check(password: str) -> None:
    """Verify against a throwaway hash so timing does not reveal user existence.

    Argon2 verification is deliberately slow. Without this, an unknown email
    would return faster than a known email with a wrong password, which is a
    user-enumeration oracle. The hash is built once, on first use, from a random
    value that is never stored.
    """
    global _uncached_dummy_hash
    if _uncached_dummy_hash is None:
        _uncached_dummy_hash = _hasher.hash(secrets.token_urlsafe(32))
    verify_password(password, _uncached_dummy_hash)
