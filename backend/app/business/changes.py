"""Change-scan orchestrator: discover new Pokémon, diff existing ones, detect new
upstream types, and compute the per-user alert feed.

**Pragmatic exception to the "business never imports from `app.db`" rule (ADR-037):**
this orchestrator coordinates several DB writes in one transactional unit (read
catalog ids → fetch+normalize via the external client → diff vs the stored row →
INSERT a change event AND mutate the row in place). A per-row repo facade around
that would be ceremony around `session.get`/`session.add`, so we keep the ORM
imports here and document the carve-out. The translation that crosses the
business boundary (the alert feed → `list[Alert]`) is still done here so the
router only ever sees business objects.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.business.alert import Alert
from app.business.pokemon import Pokemon
from app.business.snapshots import diff_snapshots, normalize_pokemon
from app.business.type_chart import get_type_chart
from app.db.models import (
    ChangeEventRow,
    PokemonRow,
    TeamMemberRow,
    TeamRow,
)
from app.db.seed import NON_BATTLE_TYPES

logger = logging.getLogger(__name__)


# --- helpers ---------------------------------------------------------------


def _id_from_ref_url(url: str) -> int | None:
    """PokéAPI list refs include only `{name, url}`; the numeric id is the URL's last
    path segment (e.g. `.../pokemon/25/` → 25). Returns None on a malformed url."""
    try:
        return int(url.rstrip("/").rsplit("/", 1)[-1])
    except (ValueError, IndexError):
        return None


async def _all_catalog_ids(session: AsyncSession) -> list[int]:
    """Every PokéAPI id our catalog currently stores."""
    rows = await session.execute(select(PokemonRow.id))
    return [pid for (pid,) in rows.all()]


def _pokemon_from_row(row: PokemonRow) -> Pokemon:
    """Translate a `PokemonRow` to the business `Pokemon` (mirrors the helper on
    `SqlPokemonRepository`; duplicated here only because changes.py keeps its DB
    imports as a pragmatic carve-out — see module docstring)."""
    return Pokemon(
        id=row.id,
        name=row.name,
        types=tuple(row.types),
        hp=row.hp,
        attack=row.attack,
        defense=row.defense,
        special_attack=row.special_attack,
        special_defense=row.special_defense,
        speed=row.speed,
        sprite_url=row.sprite_url,
        is_legendary=row.is_legendary,
        is_mythical=row.is_mythical,
    )


# --- the three passes the scheduler / admin endpoint orchestrate -----------


async def discover_new_pokemon(session: AsyncSession, client) -> int:
    """Add Pokémon ids PokéAPI knows about that our catalog doesn't, as new rows.

    Closes the "whole new generation appears" edge case (DECISIONS.md ADR-036): without
    this pass, `scan_for_changes` would only re-fetch already-stored ids and never
    enlarge the catalog. Cheap when nothing's new (one list call + a set difference =
    empty); per-Pokémon fetch failures are swallowed so a transient error doesn't abort
    the whole pass.
    """
    refs = await client.list_pokemon_refs()
    upstream_ids = {
        pid
        for ref in refs
        if (pid := _id_from_ref_url(ref.get("url", ""))) is not None
    }
    existing_ids = set(await _all_catalog_ids(session))
    new_ids = sorted(upstream_ids - existing_ids)
    if not new_ids:
        return 0
    inserted = 0
    for pid in new_ids:
        try:
            raw = await client.get_pokemon(pid)
            doc = normalize_pokemon(raw)
            species_url = (raw.get("species") or {}).get("url")
            if species_url:
                try:
                    species = await client.get_species(species_url)
                    doc["is_legendary"] = species.get("is_legendary", False)
                    doc["is_mythical"] = species.get("is_mythical", False)
                except Exception:  # noqa: BLE001 — missing flags default to False
                    pass
            session.add(PokemonRow.from_normalized(doc))
            inserted += 1
        except Exception:  # noqa: BLE001 — skip a single bad fetch; keep going
            continue
    if inserted:
        await session.commit()
    return inserted


async def scan_for_changes(session: AsyncSession, client) -> int:
    """Re-fetch every catalog Pokémon, diff against the stored snapshot, and record a
    `ChangeEventRow` for each change. Returns the number of events created.

    Was team-members-only; now scans the **whole catalog** (ADR-036) so a stat tweak to a
    Pokémon nobody currently teams is still caught — and a user who later adds that
    Pokémon will see the alert (the per-user alert filter in `recent_alerts_for_user`
    handles "is this *yours*?"). At ~1300 fetches/hour this is heavy on paper; the HTTP
    client's bounded concurrency (semaphore) + tenacity backoff keep it well under
    PokéAPI's rate budget for a single instance. A rolling slice (oldest-`fetched_at`
    first, plus always-team-members) is the obvious next step if load matters.
    """
    created = 0
    for pid in await _all_catalog_ids(session):
        pokemon = await session.get(PokemonRow, pid)
        if pokemon is None:
            continue
        try:
            raw = await client.get_pokemon(pid)
        except Exception:  # noqa: BLE001 — a transient/missing fetch shouldn't abort the scan
            continue
        new = normalize_pokemon(raw)
        diff = diff_snapshots(pokemon.snapshot, new)
        if diff:
            session.add(ChangeEventRow(pokemon_id=pid, diff=diff))
            pokemon.apply_normalized(new)
            created += 1
    if created:
        await session.commit()
    return created


async def detect_new_types(client) -> list[str]:
    """Return Pokémon types PokéAPI knows about that aren't in our loaded chart.

    The chart is a committed fixture loaded as a process-wide singleton
    (`business.type_chart`), so a hot-swap would need a module reload + global flush.
    The right amount of engineering here is **detection + a warning log** so the operator
    can refresh the fixture (`python -m app.db.seed types`) and restart — types change
    once a decade. The function is pure-ish (touches no DB) and returns the new names
    so the admin endpoint and tests can assert on them (ADR-036).
    """
    upstream = {n for n in await client.list_type_names() if n not in NON_BATTLE_TYPES}
    known = set(get_type_chart().types)
    new = sorted(upstream - known)
    if new:
        logger.warning(
            "Change scan: new Pokémon type(s) detected upstream: %s — refresh the "
            "fixture with `python -m app.db.seed types` and restart to load them.",
            new,
        )
    return new


async def scan_all(session: AsyncSession, client) -> dict:
    """Orchestrate the full periodic scan: discover new species, diff existing ones,
    detect new types. Single entrypoint for both the scheduler and `POST /admin/scan-
    changes`, so they always do the same work."""
    discovered = await discover_new_pokemon(session, client)
    changed = await scan_for_changes(session, client)
    new_types = await detect_new_types(client)
    return {"discovered": discovered, "changed": changed, "new_types": new_types}


# --- alert read-side + dev hook --------------------------------------------


async def recent_alerts_for_user(
    session: AsyncSession, user_id: str, days: int = 7
) -> list[Alert]:
    """The user's last-`days` Pokémon-change alerts as a list of business `Alert`s.

    Computed on demand by joining `change_events` to the user's team members (no
    `alerts` table). The row → business translation happens here so the router
    only ever sees business objects.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    user_pokemon = (
        select(TeamMemberRow.pokemon_id).join(TeamRow).where(TeamRow.user_id == user_id)
    )
    stmt = (
        select(ChangeEventRow)
        .options(selectinload(ChangeEventRow.pokemon))
        .where(
            ChangeEventRow.detected_at >= since,
            ChangeEventRow.pokemon_id.in_(user_pokemon),
        )
        .order_by(ChangeEventRow.detected_at.desc())
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return [
        Alert(
            pokemon=_pokemon_from_row(row.pokemon),
            detected_at=row.detected_at,
            diff=row.diff,
        )
        for row in rows
    ]


async def simulate_change(session: AsyncSession, pokemon_id: int) -> Alert | None:
    """Dev-only: record a synthetic, realistic change so the alert UI is demoable
    offline (real PokéAPI changes are rare). Drops Speed by 10."""
    pokemon = await session.get(PokemonRow, pokemon_id)
    if pokemon is None:
        return None
    old_stats = dict(pokemon.stats)
    new_stats = dict(old_stats)
    new_stats["speed"] = max(0, new_stats.get("speed", 0) - 10)
    event = ChangeEventRow(
        pokemon_id=pokemon_id,
        diff={"stats": {"old": old_stats, "new": new_stats}},
    )
    session.add(event)
    await session.commit()
    return Alert(
        pokemon=_pokemon_from_row(pokemon),
        detected_at=event.detected_at,
        diff=event.diff,
    )
