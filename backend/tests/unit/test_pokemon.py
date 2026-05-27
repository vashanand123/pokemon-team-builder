"""Unit tests for the business `Pokemon` dataclass — the computed views."""

import pytest

from app.business.pokemon import Pokemon


def _pokemon(**overrides) -> Pokemon:
    """Build a Pokemon with sensible defaults; tests override what they care about."""
    defaults = dict(
        id=1, name="x", types=("normal",),
        hp=80, attack=80, defense=80,
        special_attack=80, special_defense=80, speed=80,
    )
    defaults.update(overrides)
    return Pokemon(**defaults)


pytestmark = pytest.mark.unit


def test_stats_and_bst_views():
    p = _pokemon(hp=10, attack=20, defense=30, special_attack=40,
                 special_defense=50, speed=60)
    assert p.stats == {
        "hp": 10, "attack": 20, "defense": 30,
        "special_attack": 40, "special_defense": 50, "speed": 60,
    }
    assert p.bst == 210


def test_cp_is_monotonic_in_stats_used():
    # CP (paper eq. 2) uses max(atk, spa), max(def, spd), hp — all monotonic.
    weak = _pokemon(id=1, attack=40, special_attack=40, defense=40,
                    special_defense=40, hp=40)
    strong = _pokemon(id=2, attack=140, special_attack=140, defense=110,
                      special_defense=110, hp=120)
    assert strong.cp > weak.cp > 0


def test_snapshot_uses_list_for_types_for_diff_equality():
    """The change-scan compares the business Pokemon's snapshot to the dict
    `normalize_pokemon` produces — `types` must be a list both sides."""
    snap = _pokemon(types=("grass", "poison")).snapshot
    assert snap["types"] == ["grass", "poison"]
    assert isinstance(snap["types"], list)


def test_pokemon_is_hashable_for_solver_sets():
    """The GA puts Pokemon ids in sets; the dataclass itself is frozen so it
    could also go into a set — locking this in so future field additions don't
    silently remove hashability."""
    a = _pokemon(id=1)
    b = _pokemon(id=1)
    assert hash(a) == hash(b)
