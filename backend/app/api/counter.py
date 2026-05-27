import random

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import (
    get_counter_repo,
    get_counter_strategy,
    get_current_user,
    get_pokemon_repo,
    get_team_repo,
)
from app.business.pokemon import Pokemon
from app.business.strategy import has_duplicate_type_sets
from app.business.user import User
from app.core.config import MAX_COUNTERS_PER_TEAM
from app.schemas import (
    CounterPreviewOut,
    GenerateCounterRequest,
    SaveCounterRequest,
    SavedCounterOut,
)

router = APIRouter(prefix="/api", tags=["counter"])


async def _load_team_for_counter(team_id: str, user_id: str, team_repo):
    """Load the source team (user-scoped) and reject empty teams. Returns the business
    `Team`; raises 404 if missing/foreign, 400 if empty."""
    team = await team_repo.get_for_user(team_id, user_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    if not team.members:
        raise HTTPException(status_code=400, detail="Cannot counter an empty team")
    return team


@router.post("/teams/{team_id}/counters/generate", response_model=CounterPreviewOut)
async def generate_counter(
    team_id: str,
    body: GenerateCounterRequest,
    user: User = Depends(get_current_user),
    team_repo=Depends(get_team_repo),
    pokemon_repo=Depends(get_pokemon_repo),
    counter_repo=Depends(get_counter_repo),
    strategy=Depends(get_counter_strategy),
):
    """Evolve a counter team (Genetic Algorithm) WITHOUT persisting it — a preview.

    The search is stochastic, so each call "wiggles" to a different team; we also exclude
    teams already saved for this source team, so repeated generations stay unique.
    """
    team = await _load_team_for_counter(team_id, user.id, team_repo)
    opponent = [m.pokemon for m in team.members]  # already business Pokemon
    pool = await pokemon_repo.get_base_species_pool(include_forms=body.include_forms)
    exclude = tuple(await counter_repo.saved_member_id_sets(user.id, team_id))

    team_mons, breakdown = strategy.counter_team(
        opponent, pool, rng=random.Random(), exclude=exclude
    )
    return {
        "team": list(team_mons),
        "score": breakdown,
        "team_bst": sum(m.bst for m in team_mons),
        "opponent_bst": sum(m.bst for m in opponent),
    }


@router.post("/teams/{team_id}/counters", response_model=SavedCounterOut, status_code=201)
async def save_counter(
    team_id: str,
    body: SaveCounterRequest,
    user: User = Depends(get_current_user),
    team_repo=Depends(get_team_repo),
    pokemon_repo=Depends(get_pokemon_repo),
    counter_repo=Depends(get_counter_repo),
    strategy=Depends(get_counter_strategy),
):
    """Persist a generated counter. The score is recomputed server-side from the submitted
    members (the fitness is deterministic — only the GA search was stochastic). The team
    must be type-diverse (one of each type) and not already saved for this source team."""
    team = await _load_team_for_counter(team_id, user.id, team_repo)
    if await counter_repo.count_for_team(user.id, team_id) >= MAX_COUNTERS_PER_TEAM:
        raise HTTPException(
            status_code=409,
            detail=f"Counter limit reached (max {MAX_COUNTERS_PER_TEAM} per team)",
        )

    if len(set(body.member_ids)) != len(body.member_ids):
        raise HTTPException(status_code=400, detail="Duplicate Pokémon in counter team")

    # Resolve member ids → business Pokemon via the catalog repo; missing → 400.
    requested = list(body.member_ids)
    fetched = [await pokemon_repo.get(pid) for pid in requested]
    missing = [pid for pid, p in zip(requested, fetched) if p is None]
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown Pokémon ids: {missing}")
    team_mons: list[Pokemon] = [p for p in fetched if p is not None]

    if has_duplicate_type_sets(team_mons):
        raise HTTPException(
            status_code=400,
            detail="A counter team cannot contain two Pokémon with the same type combination",
        )

    existing = await counter_repo.saved_member_id_sets(user.id, team_id)
    if any(s == set(body.member_ids) for s in existing):
        raise HTTPException(status_code=409, detail="This counter team is already saved")

    opponent = [m.pokemon for m in team.members]
    breakdown = strategy.evaluate(team_mons, opponent)  # deterministic recompute

    return await counter_repo.create(
        user_id=user.id,
        source_team_id=team_id,
        mode="freeform",  # modes were removed; column retained for back-compat
        member_ids=requested,
        score=breakdown,
        team_bst=sum(m.bst for m in team_mons),
        opponent_bst=sum(m.bst for m in opponent),
    )


@router.get("/teams/{team_id}/counters", response_model=list[SavedCounterOut])
async def list_counters(
    team_id: str,
    user: User = Depends(get_current_user),
    team_repo=Depends(get_team_repo),
    counter_repo=Depends(get_counter_repo),
):
    """`GET /api/teams/{team_id}/counters` — saved counters for this source team,
    newest first. 404 if the source team is missing or not yours."""
    team = await team_repo.get_for_user(team_id, user.id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return await counter_repo.list_for_team(user.id, team_id)


@router.delete("/counters/{counter_id}", status_code=204)
async def delete_counter(
    counter_id: str,
    user: User = Depends(get_current_user),
    counter_repo=Depends(get_counter_repo),
):
    """`DELETE /api/counters/{id}` — hard-delete a saved counter. User-scoped: 404
    if not yours (no existence leak). Returns 204 No Content."""
    deleted = await counter_repo.delete(counter_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Counter team not found")
