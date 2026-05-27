"""Integration tests for the auth flow: signup → me → protected → logout → 401.

Each test uses the `api_client` fixture, which guarantees a freshly seeded DB
and an empty users/sessions table — no username collisions across tests.
"""

import pytest

pytestmark = pytest.mark.integration

USERNAME = "demo_user"
PASSWORD = "secret123"


def test_signup_logs_in_and_me_returns_the_user(api_client):
    r = api_client.post(
        "/api/auth/signup", json={"username": USERNAME, "password": PASSWORD}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["username"] == USERNAME
    # The cookie set by signup is enough to read /me without sending creds.
    me = api_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == USERNAME


def test_duplicate_signup_is_409(api_client):
    assert api_client.post(
        "/api/auth/signup", json={"username": USERNAME, "password": PASSWORD}
    ).status_code == 201
    again = api_client.post(
        "/api/auth/signup", json={"username": USERNAME, "password": PASSWORD}
    )
    assert again.status_code == 409


def test_login_with_wrong_password_is_401_same_detail_as_unknown_username(api_client):
    api_client.post(
        "/api/auth/signup", json={"username": USERNAME, "password": "rightpass1"}
    )
    api_client.post("/api/auth/logout")  # drop the signup-issued session

    bad_pw = api_client.post(
        "/api/auth/login", json={"username": USERNAME, "password": "wrongpass"}
    )
    unknown = api_client.post(
        "/api/auth/login",
        json={"username": "ghost_user", "password": "anything123"},
    )
    # Both 401 with the same detail — no username-existence leak.
    assert bad_pw.status_code == 401
    assert unknown.status_code == 401
    assert bad_pw.json()["detail"] == unknown.json()["detail"]


def test_username_lookup_is_case_insensitive(api_client):
    """Storage + login both lowercase the username, so 'Alice' / 'alice' / 'ALICE'
    are the same account. ADR-041."""
    api_client.post(
        "/api/auth/signup", json={"username": "Alice", "password": PASSWORD}
    )
    api_client.post("/api/auth/logout")
    # Different case still logs in.
    r = api_client.post(
        "/api/auth/login", json={"username": "ALICE", "password": PASSWORD}
    )
    assert r.status_code == 200
    assert r.json()["username"] == "alice"  # stored lowercase


def test_protected_routes_401_without_session_and_200_after_signup(api_client):
    assert api_client.get("/api/teams").status_code == 401

    api_client.post(
        "/api/auth/signup", json={"username": USERNAME, "password": PASSWORD}
    )
    assert api_client.get("/api/teams").status_code == 200
    assert api_client.get("/api/teams").json() == []  # fresh user owns nothing


def test_logout_revokes_session_and_subsequent_requests_are_401(api_client):
    api_client.post(
        "/api/auth/signup", json={"username": USERNAME, "password": PASSWORD}
    )
    assert api_client.get("/api/auth/me").status_code == 200

    assert api_client.post("/api/auth/logout").status_code == 204
    assert api_client.get("/api/auth/me").status_code == 401


def test_catalog_is_public_no_login_required(api_client):
    """Catalog routes must remain reachable without a session."""
    assert api_client.get("/api/pokemon", params={"limit": 1}).status_code == 200
    assert api_client.get("/api/pokemon/1").status_code == 200
    assert api_client.get("/healthz").status_code == 200


def test_short_password_is_rejected_by_pydantic_422(api_client):
    r = api_client.post(
        "/api/auth/signup", json={"username": USERNAME, "password": "short"}
    )
    # MIN_PASSWORD_LENGTH = 8 → Pydantic rejects at the boundary.
    assert r.status_code == 422


def test_short_username_is_rejected_by_pydantic_422(api_client):
    """MIN_USERNAME_LENGTH = 3 → 1- and 2-char usernames bounce at Pydantic."""
    r = api_client.post(
        "/api/auth/signup", json={"username": "ab", "password": PASSWORD}
    )
    assert r.status_code == 422
