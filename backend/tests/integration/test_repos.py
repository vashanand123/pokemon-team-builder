"""Repo-level integration tests — verify each SQL adapter returns business
objects and scopes correctly (the 404-as-secrecy boundary lives here, not in
the routers). Uses the `session` fixture (empty DB) and inserts the minimum
rows each test needs."""

import pytest

from app.adapters.auth_repo import DbSessionStore, SqlAuthRepository
from app.adapters.counter_repo import SqlCounterRepository
from app.adapters.pokemon_repo import SqlPokemonRepository
from app.adapters.team_repo import SqlTeamRepository
from app.business.auth import Argon2PasswordHasher
from app.business.counter_team import CounterTeam
from app.business.pokemon import Pokemon
from app.business.team import Team
from app.db.models import PokemonRow

pytestmark = pytest.mark.integration


def _pokemon_doc(pid: int, name: str = "bulbasaur") -> dict:
    return {
        "id": pid,
        "name": name,
        "types": ["grass", "poison"],
        "stats": {
            "hp": 45, "attack": 49, "defense": 49,
            "special_attack": 65, "special_defense": 65, "speed": 45,
        },
        "sprite_url": f"http://x/{pid}.png",
    }


async def _seed_pokemon(session, *ids: int) -> None:
    for pid in ids:
        session.add(PokemonRow.from_normalized(_pokemon_doc(pid)))
    await session.commit()


async def _signup(session, username: str = "demo_user") -> str:
    """Helper: signup directly via the repo; returns the new user's id."""
    hasher = Argon2PasswordHasher()
    repo = SqlAuthRepository(session)
    user = await repo.create_user(username, hasher.hash("password123"))
    return user.id


# --- pokemon repo: list/get/base-species pool ------------------------------


async def test_pokemon_repo_get_returns_business_pokemon(session):
    await _seed_pokemon(session, 1)
    repo = SqlPokemonRepository(session)
    p = await repo.get(1)
    assert isinstance(p, Pokemon)
    assert p.id == 1 and p.name == "bulbasaur"
    # The Pokemon's computed views work — i.e. we're not silently handing back
    # a row that just happens to have matching attributes.
    assert p.bst == 45 + 49 + 49 + 65 + 65 + 45


async def test_pokemon_repo_get_returns_none_for_missing(session):
    repo = SqlPokemonRepository(session)
    assert await repo.get(99999) is None


async def test_pokemon_repo_base_pool_excludes_forms_by_default(session):
    # 1 is base species; 10001 is a form (id > BASE_SPECIES_MAX_ID = 1025).
    await _seed_pokemon(session, 1)
    session.add(PokemonRow.from_normalized(_pokemon_doc(10001, name="mega-bulbasaur")))
    await session.commit()

    repo = SqlPokemonRepository(session)
    base = await repo.get_base_species_pool()
    assert {p.id for p in base} == {1}

    with_forms = await repo.get_base_species_pool(include_forms=True)
    assert {p.id for p in with_forms} == {1, 10001}


# --- team repo: scoping returns None across users --------------------------


async def test_team_repo_scoping_returns_none_for_foreign_user(session):
    await _seed_pokemon(session, 1)
    a = await _signup(session, "alice")
    b = await _signup(session, "bob")

    team_repo = SqlTeamRepository(session)
    team = await team_repo.create(a, "A's team", [1])
    assert isinstance(team, Team)

    # User b can't see user a's team — that's the 404-as-secrecy boundary.
    assert await team_repo.get_for_user(team.id, b) is None
    assert await team_repo.list_for_user(b) == []
    # Update/delete from b also no-op.
    assert await team_repo.update(team.id, b, name="hijack") is None
    assert await team_repo.delete(team.id, b) is False


async def test_team_repo_update_clears_and_replaces_members_transactionally(session):
    await _seed_pokemon(session, 1, 4, 7)
    user_id = await _signup(session)
    team_repo = SqlTeamRepository(session)
    team = await team_repo.create(user_id, "T", [1, 4, 7])
    assert [m.pokemon.id for m in team.members] == [1, 4, 7]

    updated = await team_repo.update(team.id, user_id, member_ids=[7, 1])
    assert updated is not None
    assert [m.pokemon.id for m in updated.members] == [7, 1]


# --- counter repo: list translates to business shape; saved sets are cheap -


async def test_counter_repo_create_and_list_return_business_counter_team(session):
    await _seed_pokemon(session, 25)
    user_id = await _signup(session)
    team_repo = SqlTeamRepository(session)
    team = await team_repo.create(user_id, "T", [25])

    counter_repo = SqlCounterRepository(session)
    saved = await counter_repo.create(
        user_id=user_id,
        source_team_id=team.id,
        mode="freeform",
        member_ids=[25],
        score={"fitness": 0.0, "win_rate": 0.0, "team_cp": 1, "opponent_cp": 1},
        team_bst=10,
        opponent_bst=10,
    )
    assert isinstance(saved, CounterTeam)
    # `team` was resolved from `member_ids` against the catalog in one batched query.
    assert len(saved.team) == 1
    assert saved.team[0].id == 25
    assert isinstance(saved.team[0], Pokemon)

    listed = await counter_repo.list_for_team(user_id, team.id)
    assert [c.id for c in listed] == [saved.id]


async def test_counter_repo_saved_member_id_sets_is_cheap_and_matches_create(session):
    """`saved_member_id_sets` skips the full row + catalog join (just member_ids)
    so the GA's `exclude` argument can be built quickly."""
    await _seed_pokemon(session, 25)
    user_id = await _signup(session)
    team = await SqlTeamRepository(session).create(user_id, "T", [25])
    counter_repo = SqlCounterRepository(session)
    await counter_repo.create(
        user_id=user_id, source_team_id=team.id, mode="freeform",
        member_ids=[25],
        score={}, team_bst=0, opponent_bst=0,
    )
    sets = await counter_repo.saved_member_id_sets(user_id, team.id)
    assert sets == [frozenset({25})]


# --- session store: lookup is None for revoked + unknown -------------------


async def test_session_store_lookup_returns_user_then_none_after_revoke(session):
    user_id = await _signup(session)
    store = DbSessionStore(session)
    token, _expires = await store.create(user_id)

    user = await store.lookup(token)
    assert user is not None and user.id == user_id

    await store.revoke(token)
    assert await store.lookup(token) is None


async def test_session_store_lookup_returns_none_for_unknown_token(session):
    assert await DbSessionStore(session).lookup("not-a-real-token") is None
