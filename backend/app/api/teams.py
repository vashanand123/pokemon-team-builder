from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import (
    get_counter_strategy,
    get_current_user,
    get_pokemon_repo,
    get_team_repo,
)
from app.business.strategy import has_duplicate_type_sets
from app.business.user import User
from app.core.config import MAX_TEAMS_PER_USER
from app.schemas import TeamCreate, TeamOut, TeamUpdate

router = APIRouter(prefix="/api/teams", tags=["teams"])


async def _validate_members(team_repo, pokemon_repo, ids: list[int]) -> None:
    """Reject member lists with duplicates, unknown ids, or overlapping types
    before they hit the DB.

    Three semantic checks, in order of cheapness:
      1. Duplicate Pokémon ids (set-equality, no I/O).
      2. Unknown ids (one SELECT against the catalog).
      3. Duplicate type *sets* — ADR-043 (softens ADR-042/034): two Pokémon
         with the IDENTICAL type set (e.g. both grass/poison) are rejected,
         but two that share *one* type while differing on another
         (Charizard fire/flying + Pidgeot normal/flying) are allowed. One
         batched fetch of the Pokémon + a single-pass set-of-frozenset check.

    Raises HTTPException(400) on any failure. The team-*size* cap (6) is
    enforced earlier by Pydantic at the schema boundary, not here.
    """
    if not ids:
        return
    if len(set(ids)) != len(ids):
        raise HTTPException(
            status_code=400, detail="A team cannot contain duplicate Pokémon"
        )
    existing = await team_repo.existing_pokemon_ids(ids)
    missing = [i for i in ids if i not in existing]
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown Pokémon ids: {missing}")
    # Type-diversity check (ADR-043 soft rule): same predicate as counter save.
    by_id = await pokemon_repo.get_many(ids)
    if has_duplicate_type_sets([by_id[i] for i in ids]):
        raise HTTPException(
            status_code=400,
            detail="A team cannot contain two Pokémon with the same type combination",
        )


@router.get("", response_model=list[TeamOut])
async def list_teams(
    user: User = Depends(get_current_user),
    repo=Depends(get_team_repo),
):
    """`GET /api/teams` — every team the current user owns, oldest first."""
    return await repo.list_for_user(user.id)


@router.post("", response_model=TeamOut, status_code=201)
async def create_team(
    body: TeamCreate,
    user: User = Depends(get_current_user),
    repo=Depends(get_team_repo),
    pokemon_repo=Depends(get_pokemon_repo),
):
    """`POST /api/teams` — create a team. Returns 201 with the new team.
    Errors: 409 if the user already has `MAX_TEAMS_PER_USER` teams; 400 on
    duplicate ids, unknown ids, or overlapping types (via `_validate_members`,
    ADR-042); 422 on bad body shape (Pydantic)."""
    if await repo.count_for_user(user.id) >= MAX_TEAMS_PER_USER:
        raise HTTPException(
            status_code=409,
            detail=f"Team limit reached (max {MAX_TEAMS_PER_USER} per user)",
        )
    await _validate_members(repo, pokemon_repo, body.member_ids)
    return await repo.create(user.id, body.name, body.member_ids)


@router.get("/{team_id}", response_model=TeamOut)
async def get_team(
    team_id: str,
    user: User = Depends(get_current_user),
    repo=Depends(get_team_repo),
):
    """`GET /api/teams/{id}` — one team by id. 404 if missing OR not owned by the
    current user (we return 404 rather than 403 so the API doesn't leak the
    existence of other users' teams)."""
    team = await repo.get_for_user(team_id, user.id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


@router.put("/{team_id}", response_model=TeamOut)
async def update_team(
    team_id: str,
    body: TeamUpdate,
    user: User = Depends(get_current_user),
    repo=Depends(get_team_repo),
    pokemon_repo=Depends(get_pokemon_repo),
):
    """`PUT /api/teams/{id}` — rename and/or replace the whole member list.
    Either or both of `name` and `member_ids` may be sent; what's omitted is
    left alone. Member rewrite is transactional (see `SqlTeamRepository.update`).
    Type-diversity check (ADR-042) applies the same as create."""
    if body.member_ids is not None:
        await _validate_members(repo, pokemon_repo, body.member_ids)
    updated = await repo.update(
        team_id, user.id, name=body.name, member_ids=body.member_ids
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return updated


@router.delete("/{team_id}", status_code=204)
async def delete_team(
    team_id: str,
    user: User = Depends(get_current_user),
    repo=Depends(get_team_repo),
):
    """`DELETE /api/teams/{id}` — hard-delete a team. The DB-level `ON DELETE CASCADE`
    on `team_members` + `counter_teams` removes their rows too. Returns 204 No Content."""
    deleted = await repo.delete(team_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Team not found")


@router.post("/{team_id}/autofill", response_model=TeamOut)
async def autofill_team(
    team_id: str,
    user: User = Depends(get_current_user),
    repo=Depends(get_team_repo),
    pokemon_repo=Depends(get_pokemon_repo),
    strategy=Depends(get_counter_strategy),
):
    """`POST /api/teams/{id}/autofill` — fill the team's empty slots with the strongest
    Pokémon whose types don't overlap any current member's (greedy: prefers dual-types,
    then highest BST). Unrelated to the counter algorithm — `strategy.autofill` is a
    separate helper. Returns the updated team."""
    team = await repo.get_for_user(team_id, user.id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    current = [m.pokemon for m in team.members]  # already business Pokemon (ADR-037)
    pool = await pokemon_repo.get_base_species_pool()
    added = strategy.autofill(current, pool, size=6)
    new_ids = [m.pokemon.id for m in team.members] + [p.id for p in added]
    updated = await repo.update(team_id, user.id, member_ids=new_ids)
    assert updated is not None  # we just fetched it above
    return updated
