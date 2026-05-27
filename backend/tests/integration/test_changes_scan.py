"""Integration tests for the change-scan orchestrator + per-user alert feed.

Uses the `session` fixture (drop+create per test, empty DB) — tests pre-seed
exactly the catalog rows they need (one or two), so the real fixture's ~1,300
Pokémon don't slow things down.
"""

import pytest
from sqlalchemy import func, select

from app.business.changes import (
    detect_new_types,
    discover_new_pokemon,
    recent_alerts_for_user,
    scan_for_changes,
)
from app.db.models import (
    ChangeEventRow,
    PokemonRow,
    TeamMemberRow,
    TeamRow,
    UserRow,
)

pytestmark = pytest.mark.integration


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


def _raw_with_species(pid: int, name: str, hp: int = 50) -> dict:
    return {
        "id": pid,
        "name": name,
        "types": [{"slot": 1, "type": {"name": "normal"}}],
        "stats": [
            {"stat": {"name": "hp"}, "base_stat": hp},
            {"stat": {"name": "attack"}, "base_stat": 50},
            {"stat": {"name": "defense"}, "base_stat": 50},
            {"stat": {"name": "special-attack"}, "base_stat": 50},
            {"stat": {"name": "special-defense"}, "base_stat": 50},
            {"stat": {"name": "speed"}, "base_stat": 50},
        ],
        "sprites": {"front_default": f"http://x/{pid}.png"},
        "species": {"url": f"https://pokeapi.co/api/v2/pokemon-species/{pid}/"},
    }


class _FakePokeApiClient:
    def __init__(
        self,
        payloads: dict[int, dict] | None = None,
        refs: list[dict] | None = None,
        species: dict[int, dict] | None = None,
        type_names: list[str] | None = None,
    ) -> None:
        self._payloads = payloads or {}
        self._refs = refs or []
        self._species = species or {}
        self._type_names = type_names or []

    async def list_pokemon_refs(self) -> list[dict]:
        return self._refs

    async def get_pokemon(self, ref) -> dict:
        return self._payloads[int(ref)]

    async def get_species(self, url: str) -> dict:
        try:
            sid = int(url.rstrip("/").rsplit("/", 1)[-1])
        except (ValueError, IndexError):
            sid = 0
        return self._species.get(sid, {})

    async def list_type_names(self) -> list[str]:
        return self._type_names

    async def get_type(self, name: str) -> dict:
        return {}


# --- scan + alerts ---------------------------------------------------------


async def test_scan_records_event_and_surfaces_alert(session):
    session.add(PokemonRow.from_normalized(_snapshot(hp=45)))
    user = UserRow(username="scan_test", password_hash="x")
    session.add(user)
    await session.flush()
    team = TeamRow(user_id=user.id, name="T")
    team.members.append(TeamMemberRow(slot=0, pokemon_id=1))
    session.add(team)
    await session.commit()

    # Upstream now reports a different HP.
    created = await scan_for_changes(session, _FakePokeApiClient({1: _raw(hp=99)}))
    assert created == 1

    # `recent_alerts_for_user` returns business `Alert`s (ADR-038): pokemon is a
    # business Pokemon, not the ORM row.
    alerts = await recent_alerts_for_user(session, user.id)
    assert len(alerts) == 1
    assert alerts[0].pokemon.id == 1
    assert "stats" in alerts[0].diff
    assert alerts[0].diff["stats"]["new"]["hp"] == 99

    # Re-scanning with the same data is a no-op (snapshot was updated).
    assert await scan_for_changes(session, _FakePokeApiClient({1: _raw(hp=99)})) == 0


# --- ADR-036: discovery + whole-catalog scan + new-type detection ---


async def test_discover_inserts_unknown_upstream_ids(session):
    """A 'new generation' edge case: PokéAPI lists ids our catalog doesn't have.
    The discovery pass adds them as fresh rows (no ChangeEvent — they're new,
    not changed). ADR-036."""
    session.add(PokemonRow.from_normalized(_snapshot(hp=45)))  # only #1 in catalog
    await session.commit()

    client = _FakePokeApiClient(
        refs=[
            {"name": "bulbasaur", "url": "https://pokeapi.co/api/v2/pokemon/1/"},
            {"name": "newmon", "url": "https://pokeapi.co/api/v2/pokemon/1026/"},
        ],
        payloads={1026: _raw_with_species(1026, "newmon", hp=88)},
        species={1026: {"is_legendary": True, "is_mythical": False}},
    )

    inserted = await discover_new_pokemon(session, client)
    assert inserted == 1

    new = await session.get(PokemonRow, 1026)
    assert new is not None and new.name == "newmon"
    assert new.is_legendary is True
    # And we did NOT touch the existing row.
    total = (
        await session.execute(select(func.count()).select_from(PokemonRow))
    ).scalar_one()
    assert total == 2


async def test_scan_now_covers_unteamed_pokemon(session):
    """Regression: under the previous team-members-only loop, a stat change to a
    Pokémon nobody currently teams was invisible. The widened scan records it.
    ADR-036."""
    session.add(PokemonRow.from_normalized(_snapshot(hp=45)))  # #1, but on NO team
    await session.commit()

    created = await scan_for_changes(session, _FakePokeApiClient({1: _raw(hp=99)}))
    assert created == 1

    events = (
        await session.execute(select(func.count()).select_from(ChangeEventRow))
    ).scalar_one()
    assert events == 1


async def test_detect_new_types_reports_unknown_types():
    """The chart is a fixture singleton; this pass *detects* a new upstream type
    so the operator can refresh it. ADR-036."""
    only_known = _FakePokeApiClient(type_names=["fire", "water", "grass"])
    assert await detect_new_types(only_known) == []

    with_new = _FakePokeApiClient(
        type_names=["fire", "water", "grass", "cosmic", "shadow"]  # 'shadow' non-battle
    )
    new = await detect_new_types(with_new)
    assert new == ["cosmic"]  # 'shadow' filtered as non-battle (seed.NON_BATTLE_TYPES)
