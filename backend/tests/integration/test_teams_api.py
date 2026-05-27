"""Integration tests for the teams router."""

import pytest

from app.core.config import MAX_TEAMS_PER_USER

pytestmark = pytest.mark.integration


def _signup(client, username: str = "demo_user") -> None:
    """Sign a user up; the cookie set by signup authenticates this client."""
    resp = client.post(
        "/api/auth/signup", json={"username": username, "password": "secret123"}
    )
    assert resp.status_code == 201, resp.text


def test_signed_in_user_can_crud_a_team(api_client):
    _signup(api_client)
    # Fresh user owns nothing.
    resp = api_client.get("/api/teams")
    assert resp.status_code == 200
    assert resp.json() == []

    # Create (order preserved into slots).
    resp = api_client.post(
        "/api/teams", json={"name": "Team A", "member_ids": [1, 4, 7]}
    )
    assert resp.status_code == 201
    team = resp.json()
    assert team["name"] == "Team A"
    assert [m["slot"] for m in team["members"]] == [0, 1, 2]
    assert [m["pokemon"]["id"] for m in team["members"]] == [1, 4, 7]
    team_id = team["id"]

    # Listed for this user.
    assert len(api_client.get("/api/teams").json()) == 1

    # Rename + reorder via full member replacement.
    resp = api_client.put(
        f"/api/teams/{team_id}",
        json={"name": "Team B", "member_ids": [7, 1]},
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["name"] == "Team B"
    assert [m["pokemon"]["id"] for m in updated["members"]] == [7, 1]

    # Delete.
    assert api_client.delete(f"/api/teams/{team_id}").status_code == 204
    assert api_client.get("/api/teams").json() == []


def test_teams_scoped_per_user(api_client):
    """Two signups on the same client (logout in between) → no team leak."""
    # User 1 creates a team.
    _signup(api_client, username="alice")
    team_id = api_client.post(
        "/api/teams", json={"name": "Mine", "member_ids": [25]}
    ).json()["id"]
    api_client.post("/api/auth/logout")

    # User 2 signs up on the same client → cookie now belongs to user 2.
    _signup(api_client, username="bob")
    assert api_client.get(f"/api/teams/{team_id}").status_code == 404
    assert api_client.get("/api/teams").json() == []


def test_team_limit_enforced(api_client):
    _signup(api_client)
    for i in range(MAX_TEAMS_PER_USER):
        resp = api_client.post(
            "/api/teams", json={"name": f"T{i}", "member_ids": []}
        )
        assert resp.status_code == 201
    over = api_client.post("/api/teams", json={"name": "over", "member_ids": []})
    assert over.status_code == 409


def test_validation_rejects_oversize_and_unknown(api_client):
    _signup(api_client)
    # 7 members exceeds the 6-slot cap -> 422 from Pydantic.
    resp = api_client.post(
        "/api/teams",
        json={"name": "X", "member_ids": [1, 2, 3, 4, 5, 6, 7]},
    )
    assert resp.status_code == 422
    # Unknown Pokémon id -> 400.
    resp = api_client.post(
        "/api/teams", json={"name": "X", "member_ids": [999999]}
    )
    assert resp.status_code == 400
    # Duplicate Pokémon -> 400.
    resp = api_client.post(
        "/api/teams", json={"name": "X", "member_ids": [1, 1]}
    )
    assert resp.status_code == 400


def test_create_team_rejects_duplicate_type_sets_400(api_client):
    """ADR-043 (softens ADR-042): user teams reject IDENTICAL type sets but
    allow two members that share a single type if their full sets differ.

    Cases below:
      - [1, 4]   Bulbasaur grass/poison + Charmander fire → different sets → 201
      - [1, 2]   Bulbasaur + Ivysaur, both grass/poison → identical set → 400
      - [6, 16]  Charizard fire/flying + Pidgey normal/flying → share Flying
                 but full sets differ → 201 (pre-ADR-043 this would have 400'd)
    """
    _signup(api_client)
    ok = api_client.post(
        "/api/teams", json={"name": "Diverse", "member_ids": [1, 4]}
    )
    assert ok.status_code == 201, ok.text

    bad = api_client.post(
        "/api/teams", json={"name": "Clashing", "member_ids": [1, 2]}
    )
    assert bad.status_code == 400
    assert "type combination" in bad.json()["detail"].lower()

    # The ADR-043 win: shared single type, different full sets → allowed now.
    soft_ok = api_client.post(
        "/api/teams",
        json={"name": "FlyingPair", "member_ids": [6, 16]},
    )
    assert soft_ok.status_code == 201, soft_ok.text


def test_update_team_rejects_duplicate_type_sets_400(api_client):
    """The same ADR-043 soft rule applies to PUT — identical type sets are
    rejected, shared-single-type-different-set is allowed."""
    _signup(api_client)
    team_id = api_client.post(
        "/api/teams", json={"name": "T", "member_ids": [1]}  # bulbasaur grass/poison
    ).json()["id"]
    # Replacing with [bulbasaur, ivysaur] (both grass/poison) → identical set → 400.
    bad = api_client.put(
        f"/api/teams/{team_id}", json={"member_ids": [1, 2]}
    )
    assert bad.status_code == 400
    # Replacing with [charizard, pidgey] (both fly, different full sets) → 201.
    soft_ok = api_client.put(
        f"/api/teams/{team_id}", json={"member_ids": [6, 16]}
    )
    assert soft_ok.status_code == 200, soft_ok.text


def test_blank_team_name_is_rejected_422(api_client):
    """Pydantic field_validator strips whitespace and rejects empty names —
    `'   '` would have slipped past `min_length=1` alone."""
    _signup(api_client)
    blank = api_client.post(
        "/api/teams", json={"name": "   ", "member_ids": []}
    )
    assert blank.status_code == 422
