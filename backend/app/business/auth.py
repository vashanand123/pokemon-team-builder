"""Authentication primitives — argon2id password hashing + session-token
generation. Pure utilities; the DB adapters wire them into the request lifecycle.

The `Argon2PasswordHasher` is a class (not module-level functions) so it can be
injected through `get_password_hasher` in `api/deps.py` — that's the seam to
swap in bcrypt, a peppered Argon2, or a remote KMS verifier later (ADR-039)
without touching any router.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

# Sessions last 30 days from issue. Renewal happens on signup/login (a fresh row);
# we don't slide the expiry on every request to keep the read path one indexed lookup
# with no write. Worst case a user is silently signed out and signs in again.
SESSION_TTL = timedelta(days=30)

# Minimum password length — also enforced at the API boundary via Pydantic; kept
# here as the canonical source so a future CLI / job uses the same value.
MIN_PASSWORD_LENGTH = 8

# Username length floor + ceiling — also enforced at the API boundary. Format is
# unconstrained beyond length; the adapter lowercases on store so 'Alice' and
# 'alice' are the same account.
MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 32


class Argon2PasswordHasher:
    """Argon2id password hashing via `argon2-cffi`. Library defaults are deliberately
    sane for interactive logins (memory + iterations); we don't override them to
    avoid pinning to a tuning that might age poorly."""

    def __init__(self) -> None:
        """Construct the underlying hasher with library defaults (Argon2id, the
        OWASP-recommended variant for password storage)."""
        self._h = PasswordHasher()

    def hash(self, plain: str) -> str:
        """Hash a plaintext password. The returned string encodes the algorithm,
        parameters, salt, and digest — safe to store verbatim in a single column."""
        return self._h.hash(plain)

    def verify(self, plain: str, hashed: str) -> bool:
        """Constant-time-ish password check. Returns False on any verification
        failure (wrong password, malformed hash, etc.) rather than raising — the
        caller treats all failures the same (401, no leak of which user exists)."""
        try:
            return self._h.verify(hashed, plain)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False


def new_session_token() -> str:
    """Return a fresh 256-bit random hex string for use as a session token.

    `secrets.token_hex(32)` → 32 bytes = 256 bits of entropy, encoded as 64 hex
    chars. That's well past anything you'd brute-force online; opaque-token
    sessions don't need anything fancier (ADR-039).
    """
    return secrets.token_hex(32)
