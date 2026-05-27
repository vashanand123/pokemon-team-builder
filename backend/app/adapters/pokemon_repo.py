"""SQL adapter for the Pokémon catalog. Translates `PokemonRow` → business
`Pokemon` so callers never see the ORM (ADR-038)."""

# `from __future__ import annotations` makes all annotations lazy strings — needed
# because the `list` method below shadows the builtin `list` in class scope, which
# breaks `list[Pokemon]` annotations on later methods if evaluated eagerly.
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.pokemon import Pokemon
from app.db.models import PokemonRow

# Counter-team / auto-fill draw from base-species Pokémon only (ids <= 1025), excluding
# alternate forms / megas (PokéAPI ids > 10000) so suggestions are normal Pokémon —
# ADR-015. `include_forms=True` opens the pool to those forms (ADR-029).
BASE_SPECIES_MAX_ID = 1025

# Sortable columns; "total" is the base-stat sum.
_SORT_COLUMNS = {
    "id": PokemonRow.id,
    "name": PokemonRow.name,
    "hp": PokemonRow.hp,
    "attack": PokemonRow.attack,
    "defense": PokemonRow.defense,
    "special_attack": PokemonRow.special_attack,
    "special_defense": PokemonRow.special_defense,
    "speed": PokemonRow.speed,
}
_TOTAL = (
    PokemonRow.hp
    + PokemonRow.attack
    + PokemonRow.defense
    + PokemonRow.special_attack
    + PokemonRow.special_defense
    + PokemonRow.speed
)


def _to_business(row: PokemonRow) -> Pokemon:
    """Translate a `PokemonRow` to the business `Pokemon`. Private to the adapter —
    this is the single boundary where the ORM shape meets the domain shape."""
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


class SqlPokemonRepository:
    """SQLAlchemy implementation of the catalog repository.

    Search, type filter, and sort all run in SQL against the normalized columns;
    results are translated to business `Pokemon` before they leave the adapter.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Hold the per-request session the FastAPI dep injected (`get_session`)."""
        self._s = session

    async def list(
        self,
        *,
        q: str | None = None,
        type: str | None = None,
        sort: str = "id",
        order: str = "asc",
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[list[Pokemon], int]:
        """Paginated catalog list with optional name-contains + single-type filter, sorted
        by any stat (`hp`/`attack`/.../`special_defense`) or by the special key `"total"`
        (sum of all six stats, computed in SQL). Returns `(items, total)` — `items` are
        business `Pokemon`; `total` is the match count *before* limit/offset, so the API
        can show "N Pokémon match." All filtering and sorting happens in SQL via the
        normalized columns added in ADR-018."""
        base = select(PokemonRow)
        if q:
            base = base.where(PokemonRow.name.ilike(f"%{q}%"))
        if type:
            t = type.lower()
            base = base.where((PokemonRow.type1 == t) | (PokemonRow.type2 == t))

        total = (
            await self._s.execute(select(func.count()).select_from(base.subquery()))
        ).scalar_one()

        column = _TOTAL if sort == "total" else _SORT_COLUMNS.get(sort, PokemonRow.id)
        stmt = base.order_by(column.desc() if order == "desc" else column.asc())
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [_to_business(r) for r in rows], total

    async def get(self, pokemon_id: int) -> Pokemon | None:
        """Primary-key fetch by PokéAPI id. Returns `None` if the Pokémon isn't in our
        catalog — the router maps that to 404."""
        row = await self._s.get(PokemonRow, pokemon_id)
        return _to_business(row) if row is not None else None

    async def get_many(self, ids: list[int]) -> dict[int, Pokemon]:
        """Batched lookup by id list — single `WHERE id IN (...)` round-trip,
        returning an `{id: Pokemon}` map (ids not in the catalog are simply
        absent from the map). Used by the team validator (ADR-042) to check the
        "one of each type" rule without per-id round-trips."""
        if not ids:
            return {}
        rows = await self._s.execute(
            select(PokemonRow).where(PokemonRow.id.in_(ids))
        )
        return {r.id: _to_business(r) for r in rows.scalars().all()}

    async def get_base_species_pool(
        self, *, include_forms: bool = False
    ) -> list[Pokemon]:
        """The candidate pool the counter/autofill solvers draw from.

        By default keeps only **base species** (id ≤ 1025), excluding alternate forms /
        megas / primals (PokéAPI gives those ids > 10000) so suggestions are normal
        Pokémon — ADR-015. `include_forms=True` opens the pool to those forms so a
        counter can actually match a forms-heavy opponent team — ADR-029.

        Returns business `Pokemon`, so the solver receives exactly what it needs — no
        `to_mon` translation step (ADR-037/038).
        """
        stmt = select(PokemonRow)
        if not include_forms:
            stmt = stmt.where(PokemonRow.id <= BASE_SPECIES_MAX_ID)
        rows = list((await self._s.execute(stmt)).scalars().all())
        return [_to_business(r) for r in rows]
