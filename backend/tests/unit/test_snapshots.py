"""Unit tests for the pure snapshot helpers (`normalize_pokemon`, `diff_snapshots`)."""

import pytest

from app.business.snapshots import diff_snapshots, normalize_pokemon

pytestmark = pytest.mark.unit


def _snapshot(hp: int = 45) -> dict:
    return {
        "id": 1,
        "name": "bulbasaur",
        "types": ["grass", "poison"],
        "stats": {
            "hp": hp,
            "attack": 49,
            "defense": 49,
            "special_attack": 65,
            "special_defense": 65,
            "speed": 45,
        },
        "sprite_url": "http://x/1.png",
    }


def _raw(hp: int) -> dict:
    """A raw PokéAPI-shaped payload (what the client returns)."""
    return {
        "id": 1,
        "name": "bulbasaur",
        "types": [
            {"slot": 1, "type": {"name": "grass"}},
            {"slot": 2, "type": {"name": "poison"}},
        ],
        "stats": [
            {"stat": {"name": "hp"}, "base_stat": hp},
            {"stat": {"name": "attack"}, "base_stat": 49},
            {"stat": {"name": "defense"}, "base_stat": 49},
            {"stat": {"name": "special-attack"}, "base_stat": 65},
            {"stat": {"name": "special-defense"}, "base_stat": 65},
            {"stat": {"name": "speed"}, "base_stat": 45},
        ],
        "sprites": {"front_default": "http://x/1.png"},
    }


def test_diff_detects_each_tracked_field():
    base = _snapshot()
    assert diff_snapshots(base, base) == {}  # no-op must not alert
    assert "stats" in diff_snapshots(base, _snapshot(hp=99))
    assert "types" in diff_snapshots(base, {**base, "types": ["grass"]})
    assert "name" in diff_snapshots(base, {**base, "name": "bulbasaur-x"})
    assert "sprite_url" in diff_snapshots(
        base, {**base, "sprite_url": "http://y/1.png"}
    )


def test_normalize_maps_dashed_stat_keys_and_orders_types_by_slot():
    raw = _raw(hp=45)
    # Reverse types in the raw payload to confirm normalize sorts by slot.
    raw["types"] = list(reversed(raw["types"]))
    doc = normalize_pokemon(raw)
    assert doc["types"] == ["grass", "poison"]  # slot 1 first regardless of order
    # Underscored keys are the project convention; PokéAPI uses dashes.
    assert set(doc["stats"]) == {
        "hp", "attack", "defense",
        "special_attack", "special_defense", "speed",
    }
