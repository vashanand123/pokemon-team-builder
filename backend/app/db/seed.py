"""Seed pipeline.

Two jobs:
  * `write_fixture()` — fetch all Pokémon live and write the committed JSON fixture.
    Run manually:  uv run --directory backend python -m app.db.seed
  * `load_fixture_into_db()` — load that fixture into SQLite on startup (idempotent).

This keeps reviewer startup fast and offline while the live-fetch code path stays
real and exercised (see DECISIONS.md ADR-006).
"""

import asyncio
import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.pokeapi_client import HttpPokeApiClient
from app.business.snapshots import normalize_pokemon
from app.db.models import PokemonRow

# PokéAPI's /type endpoint lists 20 types: the 18 battle types plus two non-battle,
# game-mechanic types ("shadow", "unknown") that carry empty damage relations. We
# exclude them so the derived chart is exactly the 18 canonical types.
NON_BATTLE_TYPES = {"shadow", "unknown"}

# backend/data/*.json (live inside the backend so they're in the Docker build context)
DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "pokemon_seed.json"
TYPE_FILE = Path(__file__).resolve().parents[2] / "data" / "type_chart.json"


async def fetch_all_normalized(client) -> tuple[list[dict], list[BaseException]]:
    """Fetch + normalize every Pokémon from PokéAPI in parallel (bounded by the
    client's semaphore). For each ref, calls `/pokemon/{id}` for stats AND
    `/pokemon-species/{id}` for the legendary/mythical flags (two HTTP round trips
    per Pokémon × ~1,350 species = ~2,700 calls). Returns `(ok_docs, exceptions)` —
    exceptions are collected, not raised, so a few transient failures don't lose the
    whole pipeline."""
    refs = await client.list_pokemon_refs()

    async def one(ref: dict) -> dict:
        """Inner: fetch + normalize one Pokémon (including its species flags)."""
        raw = await client.get_pokemon(ref["url"])
        doc = normalize_pokemon(raw)
        species = await client.get_species(raw["species"]["url"])
        doc["is_legendary"] = species.get("is_legendary", False)
        doc["is_mythical"] = species.get("is_mythical", False)
        return doc

    results = await asyncio.gather(*(one(r) for r in refs), return_exceptions=True)
    ok = [r for r in results if not isinstance(r, BaseException)]
    errs = [r for r in results if isinstance(r, BaseException)]
    ok.sort(key=lambda p: p["id"])
    return ok, errs


async def write_fixture() -> int:
    """Run `fetch_all_normalized` against the live PokéAPI and write the result to the
    committed JSON fixture (`data/pokemon_seed.json`). Run manually
    (`python -m app.db.seed`) when refreshing the fixture from upstream. Returns the
    number of rows written. Failed fetches are logged + skipped."""
    async with HttpPokeApiClient() as client:
        data, errs = await fetch_all_normalized(client)
    if errs:
        print(
            f"WARNING: {len(errs)} fetch(es) failed and were skipped; e.g. {errs[0]!r}"
        )
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return len(data)


async def load_fixture_into_db(session: AsyncSession) -> int:
    """Insert fixture rows if the pokemon table is empty. Returns rows inserted."""
    existing = (
        await session.execute(select(func.count()).select_from(PokemonRow))
    ).scalar_one()
    if existing:
        return 0
    if not DATA_FILE.exists():
        return 0
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    session.add_all(PokemonRow.from_normalized(p) for p in data)
    await session.commit()
    return len(data)


async def fetch_type_chart(client) -> dict[str, dict[str, float]]:
    """Derive the 18x18 effectiveness matrix from the /type list + damage relations.

    The type list is pulled from PokéAPI (not hardcoded) and the non-battle types are
    filtered out, so the written JSON is the single source of truth for the type set.
    """
    names = [n for n in await client.list_type_names() if n not in NON_BATTLE_TYPES]
    matrix: dict[str, dict[str, float]] = {}
    for name in names:
        rel = (await client.get_type(name))["damage_relations"]
        row: dict[str, float] = {}
        for d in rel["double_damage_to"]:
            row[d["name"]] = 2.0
        for d in rel["half_damage_to"]:
            row[d["name"]] = 0.5
        for d in rel["no_damage_to"]:
            row[d["name"]] = 0.0
        matrix[name] = row
    return matrix


async def write_type_chart_fixture() -> int:
    """Run `fetch_type_chart` against the live PokéAPI and write the derived 18×18
    effectiveness matrix to `data/type_chart.json`. Run manually if PokéAPI ever adds
    a new battle type (the change-scan's `detect_new_types` will log a warning when
    that happens — see ADR-036). Returns the number of types written."""
    async with HttpPokeApiClient() as client:
        matrix = await fetch_type_chart(client)
    TYPE_FILE.parent.mkdir(parents=True, exist_ok=True)
    TYPE_FILE.write_text(json.dumps(matrix, indent=2), encoding="utf-8")
    return len(matrix)


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "all"

    async def _main() -> None:
        """Command-line entry point: refresh the Pokémon fixture, the type chart, or
        both. Defaults to both. Run via `python -m app.db.seed [all|pokemon|types]`."""
        if target in ("all", "pokemon"):
            print(f"Wrote {await write_fixture()} Pokémon to {DATA_FILE}")
        if target in ("all", "types"):
            print(f"Wrote {await write_type_chart_fixture()}-type chart to {TYPE_FILE}")

    asyncio.run(_main())
