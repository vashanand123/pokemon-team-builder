"""Integration tests for the counter router."""

import pytest

from app.core.config import MAX_COUNTERS_PER_TEAM

pytestmark = pytest.mark.integration


def _signup(client, username: str = "demo_user") -> None:
    resp = client.post(
        "/api/auth/signup", json={"username": username, "password": "secret123"}
    )
    assert resp.status_code == 201, resp.text


def _new_team(client, member_ids: list[int]) -> str:
    return client.post(
        "/api/teams", json={"name": "T", "member_ids": member_ids}
    ).json()["id"]


def _generate(client, team_id: str):
    return client.post(f"/api/teams/{team_id}/counters/generate", json={})


def _save(client, team_id: str, member_ids: list[int]):
    return client.post(
        f"/api/teams/{team_id}/counters", json={"member_ids": member_ids}
    )


def test_generate_is_a_preview_and_not_persisted(api_client):
    _signup(api_client)
    team_id = _new_team(api_client, [6, 9, 3])  # charizard, blastoise, venusaur
    preview = _generate(api_client, team_id).json()
    assert 1 <= len(preview["team"]) <= 6
    assert "id" not in preview  # a preview is not saved
    for key in ("fitness", "win_rate", "team_cp", "opponent_cp"):
        assert key in preview["score"]
    assert api_client.get(f"/api/teams/{team_id}/counters").json() == []


def test_generated_counter_has_unique_type_sets(api_client):
    """ADR-043 soft rule: the generator no longer enforces all-distinct types;
    it enforces all-distinct type *sets*. Two members may share a single type
    if their full sets differ — only IDENTICAL pairs are forbidden."""
    _signup(api_client)
    team_id = _new_team(api_client, [6, 9, 3])
    team = _generate(api_client, team_id).json()["team"]
    type_sets = [frozenset(p["types"]) for p in team]
    assert len(set(type_sets)) == len(type_sets)


def test_saving_the_same_team_twice_is_rejected(api_client):
    _signup(api_client)
    team_id = _new_team(api_client, [6, 9, 3])
    ids = [p["id"] for p in _generate(api_client, team_id).json()["team"]]
    assert _save(api_client, team_id, ids).status_code == 201
    assert _save(api_client, team_id, ids).status_code == 409


def test_save_rejects_duplicate_type_sets(api_client):
    """ADR-043 soft rule: identical type sets are still rejected (six Lapras
    or [Bulbasaur, Ivysaur] both grass/poison). Shared-single-type-different-
    set pairs are now allowed — see the GA tests for the positive case."""
    _signup(api_client)
    team_id = _new_team(api_client, [6])
    # Bulbasaur (#1) and Ivysaur (#2) are both Grass/Poison → identical set → 400.
    assert _save(api_client, team_id, [1, 2]).status_code == 400


def test_save_then_delete(api_client):
    _signup(api_client)
    team_id = _new_team(api_client, [6, 9, 3])
    ids = [p["id"] for p in _generate(api_client, team_id).json()["team"]]
    first = _save(api_client, team_id, ids)
    assert first.status_code == 201
    assert first.json()["source_team_id"] == team_id
    counter_id = first.json()["id"]
    assert api_client.delete(f"/api/counters/{counter_id}").status_code == 204
    assert api_client.get(f"/api/teams/{team_id}/counters").json() == []


def test_counter_limit_enforced(api_client):
    _signup(api_client)
    team_id = _new_team(api_client, [25])
    singles = [1, 4, 7, 10, 13, 16, 19, 21, 23, 27, 29, 32]  # > MAX, distinct species
    for pid in singles[:MAX_COUNTERS_PER_TEAM]:
        assert _save(api_client, team_id, [pid]).status_code == 201
    assert _save(api_client, team_id, [singles[MAX_COUNTERS_PER_TEAM]]).status_code == 409


def test_empty_team_rejected_and_scoped_across_users(api_client):
    _signup(api_client, username="alice")
    empty_id = _new_team(api_client, [])
    assert _generate(api_client, empty_id).status_code == 400

    team_id = _new_team(api_client, [25])
    ids = [p["id"] for p in _generate(api_client, team_id).json()["team"]]
    counter_id = _save(api_client, team_id, ids).json()["id"]

    # Logout + sign up as a second user → foreign team + counter return 404.
    api_client.post("/api/auth/logout")
    _signup(api_client, username="bob")
    assert api_client.get(f"/api/teams/{team_id}/counters").status_code == 404
    assert api_client.delete(f"/api/counters/{counter_id}").status_code == 404


def test_deleting_team_cascades_to_counters(api_client):
    _signup(api_client)
    team_id = _new_team(api_client, [1])
    ids = [p["id"] for p in _generate(api_client, team_id).json()["team"]]
    counter_id = _save(api_client, team_id, ids).json()["id"]
    assert api_client.delete(f"/api/teams/{team_id}").status_code == 204
    # The counter was cascade-deleted with the team.
    assert api_client.delete(f"/api/counters/{counter_id}").status_code == 404
