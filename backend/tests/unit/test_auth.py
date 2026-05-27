"""Unit tests for the auth primitives in `business/auth.py` — pure logic, no DB."""

import pytest

from app.business.auth import Argon2PasswordHasher, new_session_token

pytestmark = pytest.mark.unit


def test_hash_roundtrip_verifies_correct_password_and_rejects_wrong():
    h = Argon2PasswordHasher()
    hashed = h.hash("correct horse battery staple")
    assert h.verify("correct horse battery staple", hashed) is True
    assert h.verify("wrong password", hashed) is False
    # Two hashes of the same plaintext differ (argon2 generates a fresh salt).
    assert h.hash("correct horse battery staple") != hashed


def test_verify_returns_false_on_malformed_hash():
    """A garbage hash must not raise — the auth router treats all verify failures
    as a 401 with the same detail, so the hasher's contract is bool-only."""
    h = Argon2PasswordHasher()
    assert h.verify("anything", "not-actually-a-hash") is False


def test_session_token_is_hex_and_long_enough():
    """`secrets.token_hex(32)` → 64 hex chars = 256 bits of entropy."""
    token = new_session_token()
    assert len(token) == 64
    int(token, 16)  # raises if not valid hex — successful parse is the assertion
    # Two fresh tokens are different.
    assert new_session_token() != token
