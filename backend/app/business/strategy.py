"""Counter-team selection via the optimization approach from the sbgames 2020 paper
"Team Recommendation for the Pokémon GO Game Using Optimization Approaches"
(Oliveira et al., XIX SBGames).

The paper scores a candidate ("home") team against a known rival team with a fitness
that sums, over every (home × rival) pairing, a *battle* value: each Pokémon's Combat
Power (CP) scaled by its best type-effectiveness against the other (Algorithms 1–3, eq. 2).
It then searches the huge team space with a metaheuristic; of the three it compares
(ILS / GA / MA) it recommends the **Genetic Algorithm** as the best speed/quality
trade-off, so that's what we implement here.

Two project-specific constraints on top of the paper:
  * a counter team has **one of each type** (no two members share a type), and
  * repeated generations are **stochastic and unique** (the GA is seeded per call and
    can be told to avoid teams already saved) — the "generate another" variety.

This module is pure: no FastAPI, no SQLAlchemy, no I/O (functional core). After the
ADR-037 layer flatten the solver operates directly on business `Pokemon` — the
old `Mon` intermediate is gone (ADR-038).
"""

from __future__ import annotations

import random

from app.business.pokemon import Pokemon
from app.business.type_chart import TypeChart


# --- The paper's fitness (Algorithms 1–3) ----------------------------------------------


def best_against(
    chart: TypeChart, defender: Pokemon, attacker_types: tuple[str, ...]
) -> float:
    """Paper's `best_against`: the strongest type-effectiveness multiplier the attacker's
    types achieve against the defender (max over the attacker's types)."""
    return max(
        (chart.effectiveness(t, defender.types) for t in attacker_types), default=1.0
    )


def battle(chart: TypeChart, home: Pokemon, opp: Pokemon) -> float:
    """Paper's `battle` (Algorithm 2): each Pokémon's CP scaled by its best type
    effectiveness against the other; positive means `home` comes out ahead."""
    home_eff = best_against(chart, opp, home.types)  # how hard home hits opp
    opp_eff = best_against(chart, home, opp.types)  # how hard opp hits home
    return home.cp * home_eff - opp.cp * opp_eff


def fitness(chart: TypeChart, team: list[Pokemon], opponent: list[Pokemon]) -> float:
    """Paper's `fitness` (Algorithm 1): the summed battle value over every
    (home member × rival member) pairing. Higher = a stronger counter team."""
    return sum(battle(chart, home, opp) for home in team for opp in opponent)


def win_rate(chart: TypeChart, team: list[Pokemon], opponent: list[Pokemon]) -> float:
    """Fraction of head-to-head pairings the home team wins (battle > 0) — a readable
    0..1 companion to the raw (and unbounded) fitness, for the UI."""
    pairs = [(h, o) for h in team for o in opponent]
    if not pairs:
        return 0.0
    return sum(1 for h, o in pairs if battle(chart, h, o) > 0) / len(pairs)


def breakdown(chart: TypeChart, team: list[Pokemon], opponent: list[Pokemon]) -> dict:
    """The score payload returned to the API/UI (deterministic given a team)."""
    return {
        "fitness": round(fitness(chart, team, opponent), 1),
        "win_rate": round(win_rate(chart, team, opponent), 3),
        "team_cp": round(sum(m.cp for m in team)),
        "opponent_cp": round(sum(m.cp for m in opponent)),
    }


# --- Type-diversity helpers ("one of each type") ---------------------------------------


def has_overlapping_types(mons: list[Pokemon]) -> bool:
    """**Strict** rule (legacy — used by `autofill` only after ADR-043). True if
    any two members share at least one type — Charizard (fire, flying) + Pidgeot
    (normal, flying) → True because both fly.

    Why autofill keeps the strict rule: autofill's job is "complete my team with
    type variety," so suggesting Pidgeot when Charizard is already on the team
    would be UX malpractice. The save validators (teams + counters) and the GA
    use `has_duplicate_type_sets` instead — see ADR-043 for the rationale.
    """
    seen: set[str] = set()
    for m in mons:
        for t in m.types:
            if t in seen:
                return True
            seen.add(t)
    return False


def has_duplicate_type_sets(mons: list[Pokemon]) -> bool:
    """**Soft** rule (ADR-043, replaces `has_overlapping_types` for save-time
    validation and GA candidacy). True if two members have the *identical* type
    set — Bulbasaur + Ivysaur (both grass/poison) → True; Charizard (fire,
    flying) + Pidgeot (normal, flying) → False (different sets, shared single
    type is allowed).

    Why softer than strict: real competitive teams often share a single type
    across multiple members (Water-Flying offense cores, Steel-resist cores,
    mono-type-with-different-secondaries archetypes). The strict rule ruled all
    of those out, which was both over-restrictive and worse on the paper's
    fitness against type-concentrated opponents. The soft rule preserves "no
    exact duplicates" (six Lapras is still rejected) without the collateral
    damage.
    """
    seen: set[frozenset[str]] = set()
    for m in mons:
        key = frozenset(m.types)
        if key in seen:
            return True
        seen.add(key)
    return False


def _can_add(team: list[Pokemon], cand: Pokemon, chosen: set[int]) -> bool:
    """A candidate may join only if it's a new id AND its type set isn't already
    represented on the team (ADR-043 soft rule). Used by the GA's
    `_random_team` and `_crossover`; `_mutate` carries an inline equivalent."""
    if cand.id in chosen:
        return False
    used_sets = {frozenset(m.types) for m in team}
    return frozenset(cand.types) not in used_sets


def _random_team(pool: list[Pokemon], size: int, rng: random.Random) -> list[Pokemon]:
    """A random, type-diverse team (greedy fill over a shuffled pool)."""
    order = list(pool)
    rng.shuffle(order)
    team: list[Pokemon] = []
    chosen: set[int] = set()
    for cand in order:
        if len(team) >= size:
            break
        if _can_add(team, cand, chosen):
            team.append(cand)
            chosen.add(cand.id)
    return team


def _mutate(
    team: list[Pokemon], pool: list[Pokemon], rng: random.Random
) -> list[Pokemon]:
    """Replace one random member with a random pool Pokémon that keeps the team
    duplicate-free in both ids and type sets (ADR-043 soft rule)."""
    if not team:
        return team
    out = list(team)
    i = rng.randrange(len(out))
    chosen = {m.id for j, m in enumerate(out) if j != i}
    used_sets = {frozenset(m.types) for j, m in enumerate(out) if j != i}
    candidates = [
        c for c in pool if c.id not in chosen and frozenset(c.types) not in used_sets
    ]
    if candidates:
        out[i] = rng.choice(candidates)
    return out


def _crossover(
    p1: list[Pokemon],
    p2: list[Pokemon],
    pool: list[Pokemon],
    size: int,
    rng: random.Random,
) -> list[Pokemon]:
    """Single-cut crossover (paper §IV-E) with repair: take the head of one parent and the
    tail of the other, then drop duplicates / type clashes and top up from the pool, so the
    child is always a valid type-diverse team."""
    shortest = min(len(p1), len(p2))
    cut = rng.randint(1, shortest - 1) if shortest > 1 else shortest
    child: list[Pokemon] = []
    chosen: set[int] = set()
    # Prefer the cut split, then fall back to the whole parents.
    for src in (p1[:cut], p2[cut:], p1, p2):
        for m in src:
            if len(child) >= size:
                return child
            if _can_add(child, m, chosen):
                child.append(m)
                chosen.add(m.id)
    # Only if the parents couldn't fill a valid team, top up from the pool.
    if len(child) < size:
        for m in _shuffled(pool, rng):
            if len(child) >= size:
                break
            if _can_add(child, m, chosen):
                child.append(m)
                chosen.add(m.id)
    return child


def _shuffled(pool: list[Pokemon], rng: random.Random) -> list[Pokemon]:
    """Return a fresh randomly-shuffled copy of `pool` (doesn't mutate the input).
    Used by `_crossover` when topping up a child team from the pool."""
    order = list(pool)
    rng.shuffle(order)
    return order


# --- The Genetic Algorithm -------------------------------------------------------------


class GeneticCounterStrategy:
    """Genetic Algorithm over the paper's CP×effectiveness fitness. Parameters follow the
    paper's tuning (Table I): 50 individuals, 20 iterations, 80% crossover, 20% mutation,
    elitism. Every individual (team) is type-diverse; the search is stochastic so repeated
    calls "wiggle" to different teams, and `exclude` makes them guaranteed-unique.
    """

    def __init__(
        self,
        chart: TypeChart,
        individuals: int = 50,
        iterations: int = 20,
        crossover_rate: float = 0.8,
        mutation_rate: float = 0.2,
    ) -> None:
        """Hold the type chart + the GA's tunable parameters. Defaults match the
        sbgames-2020 paper's Table I (50 individuals, 20 generations, 80% crossover,
        20% mutation) — the paper's recommended trade-off between fitness and runtime."""
        self._chart = chart
        self._n = individuals
        self._iters = iterations
        self._cx = crossover_rate
        self._mut = mutation_rate

    def evaluate(self, team: list[Pokemon], opponent: list[Pokemon]) -> dict:
        """Deterministic score breakdown for an explicit team (used when saving — the
        fitness is pure, only the GA's search is stochastic)."""
        return breakdown(self._chart, team, opponent)

    def counter_team(
        self,
        opponent: list[Pokemon],
        pool: list[Pokemon],
        size: int = 6,
        rng: random.Random | None = None,
        exclude: tuple[frozenset[int], ...] = (),
    ) -> tuple[list[Pokemon], dict]:
        """Evolve a counter team against `opponent`. `exclude` is a set of member-id sets
        to avoid (already-saved teams), so "generate another" returns a *new* team."""
        rng = rng or random.Random()
        size = min(size, len(pool))
        if size == 0 or not opponent:
            return [], breakdown(self._chart, [], opponent)
        excluded = set(exclude)

        def fit(team: list[Pokemon]) -> float:
            return fitness(self._chart, team, opponent)

        def tournament(pop: list[list[Pokemon]]) -> list[Pokemon]:
            return max(rng.sample(pop, min(3, len(pop))), key=fit)

        population = sorted(
            (_random_team(pool, size, rng) for _ in range(self._n)),
            key=fit,
            reverse=True,
        )
        for _ in range(self._iters):
            nxt = [population[0]]  # elitism: keep the best individual
            while len(nxt) < self._n:
                parent = tournament(population)
                if rng.random() < self._cx:
                    child = _crossover(parent, tournament(population), pool, size, rng)
                else:
                    child = list(parent)
                if rng.random() < self._mut:
                    child = _mutate(child, pool, rng)
                nxt.append(child)
            population = sorted(nxt, key=fit, reverse=True)

        # Best team that isn't already saved; if the whole population collides, perturb.
        for team in population:
            if frozenset(m.id for m in team) not in excluded:
                return team, breakdown(self._chart, team, opponent)
        best = list(population[0])
        for _ in range(50):
            best = _mutate(best, pool, rng)
            if frozenset(m.id for m in best) not in excluded:
                break
        return best, breakdown(self._chart, best, opponent)

    def autofill(
        self,
        current: list[Pokemon],
        pool: list[Pokemon],
        size: int = 6,
        rng: random.Random | None = None,
    ) -> list[Pokemon]:
        """Fill empty slots with a random, type-diverse selection from the pool.

        No optimization — autofill's job is "give me a diverse team to play
        with," not "find the strongest team." Same call returns a *different*
        six on each click because the caller passes a fresh RNG per request.
        Uses the same shape as the GA's `_random_team` (shuffle pool, walk,
        admit non-clashing) just with the **strict** type-overlap rule (ADR-043
        carve-out — autofill's value proposition is type *variety*, so two
        members sharing any type would defeat its purpose, even though the
        ADR-043 save validators allow shared-single-type-different-set teams).
        """
        rng = rng or random.Random()
        team = list(current)
        chosen = {m.id for m in current}
        used_types = {t for m in current for t in m.types}
        added: list[Pokemon] = []
        shuffled = list(pool)
        rng.shuffle(shuffled)
        for cand in shuffled:
            if len(team) >= size:
                break
            if cand.id in chosen or (set(cand.types) & used_types):
                continue
            team.append(cand)
            chosen.add(cand.id)
            used_types |= set(cand.types)
            added.append(cand)
        return added
