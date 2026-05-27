"""SQL adapter for saved counter teams. Translates `CounterTeamRow` → business
`CounterTeam`, resolving the stored `member_ids` JSON list back to full `Pokemon`
objects in a single batched `WHERE id IN (...)` lookup (ADR-038).
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.counter_team import CounterTeam
from app.business.pokemon import Pokemon
from app.db.models import CounterTeamRow, PokemonRow


def _pokemon_from_row(row: PokemonRow) -> Pokemon:
    """Translate a `PokemonRow` to the business `Pokemon`. Local to the adapter."""
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


class SqlCounterRepository:
    """Persistence for saved counter teams. All reads are user-scoped."""

    def __init__(self, session: AsyncSession) -> None:
        """Hold the per-request session the FastAPI dep injected (`get_session`)."""
        self._s = session

    async def _resolve_pokemon(self, ids: list[int]) -> dict[int, Pokemon]:
        """Fetch the Pokémon for a flat list of ids in one round trip.

        Batched so listing N saved counters costs 2 queries (counters + Pokémon),
        not 1 + N. Returns an id→Pokemon map so each counter row can be assembled
        in member-id order.
        """
        if not ids:
            return {}
        rows = await self._s.execute(
            select(PokemonRow).where(PokemonRow.id.in_(ids))
        )
        return {r.id: _pokemon_from_row(r) for r in rows.scalars().all()}

    def _to_business(
        self, row: CounterTeamRow, by_id: dict[int, Pokemon]
    ) -> CounterTeam:
        """Translate a `CounterTeamRow` to a business `CounterTeam` using the
        pre-resolved catalog map (`_resolve_pokemon`)."""
        return CounterTeam(
            id=row.id,
            source_team_id=row.source_team_id,
            team=tuple(by_id[pid] for pid in row.member_ids),
            score=row.score,
            team_bst=row.team_bst,
            opponent_bst=row.opponent_bst,
            created_at=row.created_at,
            user_id=row.user_id,
        )

    async def count_for_team(self, user_id: str, source_team_id: str) -> int:
        """Number of counters this user has saved against this source team. Used to
        enforce `MAX_COUNTERS_PER_TEAM` (returns 409 at the cap)."""
        stmt = (
            select(func.count())
            .select_from(CounterTeamRow)
            .where(
                CounterTeamRow.user_id == user_id,
                CounterTeamRow.source_team_id == source_team_id,
            )
        )
        return (await self._s.execute(stmt)).scalar_one()

    async def saved_member_id_sets(
        self, user_id: str, source_team_id: str
    ) -> list[frozenset[int]]:
        """Cheap helper for the generator's `exclude` argument: just the sets of
        member ids already saved. Avoids loading + resolving full counter rows just
        to feed the GA's "don't repeat" parameter."""
        stmt = select(CounterTeamRow.member_ids).where(
            CounterTeamRow.user_id == user_id,
            CounterTeamRow.source_team_id == source_team_id,
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [frozenset(ids) for ids in rows]

    async def create(
        self,
        *,
        user_id: str,
        source_team_id: str,
        mode: str,
        member_ids: list[int],
        score: dict,
        team_bst: int,
        opponent_bst: int,
    ) -> CounterTeam:
        """Persist a new saved counter and return the business `CounterTeam` for
        the wire.

        Counters are no longer unique per (team, mode): generation is now stochastic
        (ADR-028), so several saves of the same style are genuinely different teams
        worth keeping side by side (bounded by MAX_COUNTERS_PER_TEAM).
        """
        row = CounterTeamRow(
            user_id=user_id,
            source_team_id=source_team_id,
            mode=mode,
            member_ids=member_ids,
            score=score,
            team_bst=team_bst,
            opponent_bst=opponent_bst,
        )
        self._s.add(row)
        await self._s.commit()
        await self._s.refresh(row)
        by_id = await self._resolve_pokemon(list(member_ids))
        return self._to_business(row, by_id)

    async def list_for_team(
        self, user_id: str, source_team_id: str
    ) -> list[CounterTeam]:
        """All saved counters this user has for this source team, newest first."""
        stmt = (
            select(CounterTeamRow)
            .where(
                CounterTeamRow.user_id == user_id,
                CounterTeamRow.source_team_id == source_team_id,
            )
            .order_by(CounterTeamRow.created_at.desc())
        )
        rows = list((await self._s.execute(stmt)).scalars().all())
        all_ids = sorted({pid for r in rows for pid in r.member_ids})
        by_id = await self._resolve_pokemon(all_ids)
        return [self._to_business(r, by_id) for r in rows]

    async def get_for_user(
        self, counter_id: str, user_id: str
    ) -> CounterTeam | None:
        """Fetch one saved counter by id, scoped to user. Returns `None` if missing
        OR not theirs — the router maps both to 404 (no existence leak)."""
        stmt = select(CounterTeamRow).where(
            CounterTeamRow.id == counter_id, CounterTeamRow.user_id == user_id
        )
        row = (await self._s.execute(stmt)).scalars().first()
        if row is None:
            return None
        by_id = await self._resolve_pokemon(list(row.member_ids))
        return self._to_business(row, by_id)

    async def delete(self, counter_id: str, user_id: str) -> bool:
        """Hard-delete a saved counter. Returns `True` if a counter was deleted,
        `False` if it didn't exist or wasn't theirs (router maps False → 404).
        The DB-level FK from `counter_teams.source_team_id` cascades the other
        direction — deleting a source team removes its counters too."""
        stmt = select(CounterTeamRow).where(
            CounterTeamRow.id == counter_id, CounterTeamRow.user_id == user_id
        )
        row = (await self._s.execute(stmt)).scalars().first()
        if row is None:
            return False
        await self._s.delete(row)
        await self._s.commit()
        return True
