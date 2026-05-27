"""Unit tests for the GA + the paper's fitness primitives."""

import random

import pytest

from app.business.pokemon import Pokemon
from app.business.strategy import (
    GeneticCounterStrategy,
    battle,
    best_against,
    fitness,
    win_rate,
)
from app.business.type_chart import TypeChart, get_type_chart

pytestmark = pytest.mark.unit


def _mon(id, name, types, atk=80, spa=80, hp=80, df=80, spd=80, spe=80):
    return Pokemon(
        id=id,
        name=name,
        types=tuple(types),
        hp=hp,
        attack=atk,
        defense=df,
        special_attack=spa,
        special_defense=spd,
        speed=spe,
    )


def _toy_chart() -> TypeChart:
    m: dict[str, dict[str, float]] = {}
    m.setdefault("water", {})["fire"] = 2.0
    m.setdefault("fire", {})["water"] = 0.5
    m.setdefault("fire", {})["grass"] = 2.0
    m.setdefault("grass", {})["fire"] = 0.5
    return TypeChart(m)


# --- Paper primitives (best_against, battle, fitness, win_rate) ------------


def test_best_against_is_max_effectiveness():
    chart = get_type_chart()
    fire = _mon(1, "fire", ("fire",))
    assert best_against(chart, fire, ("water",)) == 2.0
    assert best_against(chart, fire, ("grass",)) == 0.5


def test_battle_rewards_type_advantage_and_power():
    chart = _toy_chart()
    fire = _mon(1, "fire", ("fire",))
    water = _mon(2, "water", ("water",))
    grass = _mon(3, "grass", ("grass",))
    assert battle(chart, water, fire) > 0
    assert battle(chart, grass, fire) < 0
    # Anti-symmetric: swapping sides flips the sign.
    assert battle(chart, water, fire) == -battle(chart, fire, water)


def test_fitness_sums_over_all_pairings():
    chart = _toy_chart()
    fire = _mon(1, "fire", ("fire",))
    water = _mon(2, "water", ("water",))
    grass = _mon(3, "grass", ("grass",))
    team = [water, grass]
    opp = [fire]
    assert fitness(chart, team, opp) == battle(chart, water, fire) + battle(
        chart, grass, fire
    )


def test_win_rate_in_unit_range():
    chart = get_type_chart()
    opp = [_mon(1, "fire", ("fire",))]
    team = [_mon(2, "water", ("water",)), _mon(3, "rock", ("rock",))]
    assert 0.0 <= win_rate(chart, team, opp) <= 1.0


# --- The GA (deterministic with a seed; type-diverse; unique) --------------


def _pool() -> list[Pokemon]:
    chart = get_type_chart()
    # One representative mon per type → a type-diverse team of 6 is always buildable.
    return [_mon(i, t, (t,)) for i, t in enumerate(chart.types, start=1)]


def test_counter_team_has_unique_type_sets_and_unique_members():
    """ADR-043 (soft rule): the GA guarantees no duplicate Pokémon and no
    duplicate type *sets* — but two members CAN share a single type if their
    full sets differ (e.g. fire/flying + normal/flying). The pre-ADR-043
    strict rule used to forbid the latter."""
    strat = GeneticCounterStrategy(get_type_chart(), individuals=20, iterations=8)
    opponent = [_mon(901, "charizard", ("fire", "flying"))]
    team, score = strat.counter_team(opponent, _pool(), size=6, rng=random.Random(0))
    assert len(team) == 6
    assert len({m.id for m in team}) == 6  # no duplicate Pokémon
    # Soft rule: each member's type set is unique across the team.
    type_sets = [frozenset(m.types) for m in team]
    assert len(set(type_sets)) == len(type_sets)
    assert {"fitness", "win_rate", "team_cp", "opponent_cp"} <= set(score)


def test_counter_team_allows_shared_type_when_sets_differ():
    """ADR-043: two members sharing a single type (e.g. both fly) are now
    allowed as long as their full type *sets* differ. Pre-ADR-043 the strict
    rule would have refused to include both in the same team."""
    strat = GeneticCounterStrategy(get_type_chart(), individuals=20, iterations=8)
    opponent = [_mon(901, "tauros", ("normal",), atk=100)]
    # Pool deliberately includes TWO flying mons with different secondary types;
    # the GA must be able to pick both into the same team under ADR-043.
    pool = [
        _mon(1, "charizard", ("fire", "flying"), atk=84, spa=109),
        _mon(2, "pidgeot", ("normal", "flying"), atk=80, spa=70),
        _mon(3, "lapras", ("water", "ice"), atk=85, spa=85, hp=130),
        _mon(4, "venusaur", ("grass", "poison"), atk=82, spa=100),
        _mon(5, "alakazam", ("psychic",), spa=135, hp=55),
        _mon(6, "machamp", ("fighting",), atk=130, hp=90),
    ]
    team, _ = strat.counter_team(opponent, pool, size=6, rng=random.Random(0))
    # All six fit — including both flying mons.
    assert {m.id for m in team} == {1, 2, 3, 4, 5, 6}


def test_counter_team_excludes_already_saved():
    strat = GeneticCounterStrategy(get_type_chart(), individuals=20, iterations=8)
    opponent = [_mon(901, "fire", ("fire",))]
    pool = _pool()
    first, _ = strat.counter_team(opponent, pool, size=6, rng=random.Random(1))
    exclude = (frozenset(m.id for m in first),)
    second, _ = strat.counter_team(
        opponent, pool, size=6, rng=random.Random(1), exclude=exclude
    )
    assert {m.id for m in second} != {m.id for m in first}


def test_counter_team_is_deterministic_with_a_seed():
    strat = GeneticCounterStrategy(get_type_chart(), individuals=20, iterations=8)
    opponent = [_mon(901, "fire", ("fire",)), _mon(902, "water", ("water",))]
    pool = _pool()
    a, _ = strat.counter_team(opponent, pool, size=6, rng=random.Random(42))
    b, _ = strat.counter_team(opponent, pool, size=6, rng=random.Random(42))
    assert [m.id for m in a] == [m.id for m in b]


def test_counter_beats_a_super_effective_pick_into_the_team():
    # Against a mono-fire opponent, a strong type-diverse counter should include
    # a Water answer (positive battle) — the GA optimizes the paper's fitness.
    strat = GeneticCounterStrategy(get_type_chart(), individuals=30, iterations=12)
    opponent = [_mon(901, "charmander", ("fire",), atk=120, spa=120)]
    team, score = strat.counter_team(opponent, _pool(), size=6, rng=random.Random(3))
    assert score["fitness"] > 0
    assert any("water" in m.types for m in team)


def test_autofill_never_overlaps_types_strict_rule_preserved():
    """ADR-043 softened the SAVE-time rule but autofill DELIBERATELY keeps the
    STRICT rule — its job is "complete my team with type variety" so suggesting
    a candidate that shares a single type with an existing member would defeat
    its purpose. This test pins that semantics so a future "consolidate the
    rule" refactor can't silently flip it."""
    strat = GeneticCounterStrategy(get_type_chart())
    current = [_mon(1, "a", ("fire",)), _mon(2, "b", ("water",))]
    pool = [
        _mon(3, "c", ("fire", "flying")),  # shares fire — strict-excluded
        _mon(4, "d", ("grass",)),
        _mon(5, "e", ("electric",)),
        _mon(6, "f", ("water", "ground")),  # shares water — strict-excluded
    ]
    added = strat.autofill(current, pool, size=4)
    used = {t for m in current for t in m.types}
    for m in added:
        assert not (set(m.types) & used)
        used |= set(m.types)
    # Under the soft rule, 3 and 6 would be eligible (different type *sets*
    # from existing members). Autofill keeping the strict rule excludes them.
    assert {m.id for m in added} == {4, 5}
