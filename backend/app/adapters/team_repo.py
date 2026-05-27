"""SQL adapter for teams. Translates `TeamRow`/`TeamMemberRow` → business
`Team`/`TeamMember` so callers never see the ORM (ADR-038).

`update`/`delete` accept `(team_id, user_id)` and re-load the row inside the
adapter (vs. accepting a business `Team` and reloading by id). One extra lookup
per write, but the API is unambiguous and no ORM row leaks across the boundary.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.business.pokemon import Pokemon
from app.business.team import Team, TeamMember
from app.db.models import PokemonRow, TeamMemberRow, TeamRow


def _pokemon_from_row(row: PokemonRow) -> Pokemon:
    """Translate a `PokemonRow` to the business `Pokemon`. Local copy (vs. importing
    from `pokemon_repo`) so each adapter owns its own translation — no implicit
    coupling between repos."""
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


def _to_business(row: TeamRow) -> Team:
    """Translate a `TeamRow` (with its `members` + each member's `pokemon` eager-loaded)
    to a business `Team`. Always called against a row loaded via `_select_with_members`."""
    return Team(
        id=row.id,
        name=row.name,
        members=tuple(
            TeamMember(slot=m.slot, pokemon=_pokemon_from_row(m.pokemon))
            for m in row.members
        ),
        created_at=row.created_at,
        updated_at=row.updated_at,
        user_id=row.user_id,
    )


class SqlTeamRepository:
    """SQLAlchemy implementation of the team repository. All reads are user-scoped."""

    def __init__(self, session: AsyncSession) -> None:
        """Hold the per-request session the FastAPI dep injected (`get_session`)."""
        self._s = session

    def _select_with_members(self):
        """Base SELECT for `TeamRow` that eager-loads members + their Pokémon in one
        batched extra query (avoids the N+1 problem when translating to a business
        `Team`)."""
        return select(TeamRow).options(
            selectinload(TeamRow.members).selectinload(TeamMemberRow.pokemon)
        )

    async def _row_for_user(self, team_id: str, user_id: str) -> TeamRow | None:
        """Internal row lookup. Returns the ORM row (callers in this adapter need to
        mutate it); business code never sees this — `get_for_user` is the public
        entry point and returns a business `Team`."""
        stmt = self._select_with_members().where(
            TeamRow.id == team_id, TeamRow.user_id == user_id
        )
        return (await self._s.execute(stmt)).scalars().first()

    async def count_for_user(self, user_id: str) -> int:
        """Number of teams this user owns. Used to enforce `MAX_TEAMS_PER_USER`."""
        stmt = (
            select(func.count()).select_from(TeamRow).where(TeamRow.user_id == user_id)
        )
        return (await self._s.execute(stmt)).scalar_one()

    async def list_for_user(self, user_id: str) -> list[Team]:
        """All of a user's teams, oldest first."""
        stmt = (
            self._select_with_members()
            .where(TeamRow.user_id == user_id)
            .order_by(TeamRow.created_at)
        )
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [_to_business(r) for r in rows]

    async def get_for_user(self, team_id: str, user_id: str) -> Team | None:
        """Fetch one team by id, scoped to user. Returns `None` if missing OR not theirs
        — the security boundary that lets the router return 404 (not 403) for either case
        so we don't leak the existence of other users' teams."""
        row = await self._row_for_user(team_id, user_id)
        return _to_business(row) if row is not None else None

    async def create(self, user_id: str, name: str, member_ids: list[int]) -> Team:
        """Create a team for the user. `member_ids` map to slots 0..N in order.

        Under ADR-039 every `UserRow` is written at signup with credentials, so the
        Phase-1 "lazy user materialize on first write" dance (ADR-027) is gone —
        we just `INSERT` the team.
        """
        row = TeamRow(user_id=user_id, name=name)
        for slot, pid in enumerate(member_ids):
            row.members.append(TeamMemberRow(slot=slot, pokemon_id=pid))
        self._s.add(row)
        await self._s.commit()
        # Re-load with members + pokemon eager-loaded so the business shape is complete.
        reloaded = await self._row_for_user(row.id, user_id)
        assert reloaded is not None  # we just inserted it
        return _to_business(reloaded)

    async def update(
        self,
        team_id: str,
        user_id: str,
        *,
        name: str | None = None,
        member_ids: list[int] | None = None,
    ) -> Team | None:
        """Rename and/or replace the whole member list, transactionally. Returns
        the updated business `Team`, or `None` if the team is missing / not theirs
        (router maps to 404).

        The clear→flush→re-append dance is needed because `team_members` has a
        composite PK `(team_id, slot)`: the old rows must be DELETE'd before the
        new ones are INSERT'd, or the new slot numbers collide with the old.
        """
        row = await self._row_for_user(team_id, user_id)
        if row is None:
            return None
        if name is not None:
            row.name = name
        if member_ids is not None:
            row.members.clear()
            await self._s.flush()  # delete old rows before re-inserting (team_id, slot) PK
            for slot, pid in enumerate(member_ids):
                row.members.append(TeamMemberRow(slot=slot, pokemon_id=pid))
        await self._s.commit()
        reloaded = await self._row_for_user(team_id, user_id)
        assert reloaded is not None
        return _to_business(reloaded)

    async def delete(self, team_id: str, user_id: str) -> bool:
        """Hard-delete the team. `ON DELETE CASCADE` removes `team_members` and
        `counter_teams` too (SQLite needs `PRAGMA foreign_keys=ON`, set in
        `db/session.py`). Returns `True` if a team was deleted, `False` if the
        team didn't exist or wasn't theirs (router maps False to 404)."""
        row = await self._row_for_user(team_id, user_id)
        if row is None:
            return False
        await self._s.delete(row)
        await self._s.commit()
        return True

    async def existing_pokemon_ids(self, ids: list[int]) -> set[int]:
        """Of the given Pokémon ids, the subset that actually exist in the catalog.
        Used by the team router to give a clean 400 ("Unknown Pokémon ids: …") instead
        of letting a foreign-key constraint blow up at commit time."""
        if not ids:
            return set()
        rows = await self._s.execute(
            select(PokemonRow.id).where(PokemonRow.id.in_(ids))
        )
        return set(rows.scalars().all())
