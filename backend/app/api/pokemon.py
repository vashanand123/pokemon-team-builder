from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_pokemon_repo
from app.schemas import PokemonListOut, PokemonOut

router = APIRouter(prefix="/api/pokemon", tags=["pokemon"])


@router.get("", response_model=PokemonListOut)
async def list_pokemon(
    repo=Depends(get_pokemon_repo),
    q: str | None = Query(None, description="case-insensitive name search"),
    type: str | None = Query(None, description="filter to Pokémon having this type"),
    sort: str = Query(
        "id",
        description="id|name|total|hp|attack|defense|special_attack|special_defense|speed",
    ),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int | None = Query(None, ge=1, le=2000),
    offset: int = Query(0, ge=0),
):
    """`GET /api/pokemon` — paginated catalog list. Public (no identity required).
    Validation (`ge`/`le`/`pattern`) happens at the Pydantic boundary, so bad query params
    return 422 before this handler runs. Returns `{items, total}` where `total` is the
    match count before pagination."""
    items, total = await repo.list(
        q=q, type=type, sort=sort, order=order, limit=limit, offset=offset
    )
    return {"items": items, "total": total}


@router.get("/{pokemon_id}", response_model=PokemonOut)
async def get_pokemon(pokemon_id: int, repo=Depends(get_pokemon_repo)):
    """`GET /api/pokemon/{id}` — one Pokémon by its PokéAPI id. 404 if not in the catalog."""
    pokemon = await repo.get(pokemon_id)
    if pokemon is None:
        raise HTTPException(status_code=404, detail="Pokémon not found")
    return pokemon
