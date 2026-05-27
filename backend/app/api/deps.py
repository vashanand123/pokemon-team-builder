"""The dependency-injection composition root — *the* swap seam (ADR-022/024/037/039).

Every infrastructure choice (which DB driver, which password hasher, which session
store, which counter strategy) is named in exactly one of these provider functions.
Routers depend on the *provider*, never on the concrete class — so swapping
SQLite → Postgres, argon2 → bcrypt, DB-backed sessions → Redis, or
genetic-algorithm → some new strategy, is a one-line change here with zero churn
in any router. Tests substitute fakes via FastAPI dependency overrides.

After the ADR-037 layer flatten the repos return business objects (`business.Pokemon`,
`business.Team`, `business.User`, …) instead of ORM rows — that boundary moves
into each adapter's `_to_business` helper, but the DI surface here is unchanged.
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.auth_repo import DbSessionStore, SqlAuthRepository
from app.adapters.counter_repo import SqlCounterRepository
from app.adapters.pokemon_repo import SqlPokemonRepository
from app.adapters.team_repo import SqlTeamRepository
from app.business.auth import Argon2PasswordHasher
from app.business.strategy import GeneticCounterStrategy
from app.business.type_chart import get_type_chart
from app.business.user import User
from app.core.config import settings
from app.db.session import get_session

# --- Catalog / domain repos ------------------------------------------------


def get_pokemon_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlPokemonRepository:
    """Provider for the catalog repo. Swap return type to point at a different
    storage layer (e.g. Postgres) and no router changes."""
    return SqlPokemonRepository(session)


def get_team_repo(session: AsyncSession = Depends(get_session)) -> SqlTeamRepository:
    """Provider for the team repo."""
    return SqlTeamRepository(session)


def get_counter_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlCounterRepository:
    """Provider for the saved-counters repo."""
    return SqlCounterRepository(session)


def get_counter_strategy() -> GeneticCounterStrategy:
    """Provider for the counter algorithm — the sbgames-2020 Genetic Algorithm over
    the Combat-Power × type-effectiveness fitness (ADR-032). Swap to point at a
    different solver without touching the counter router."""
    return GeneticCounterStrategy(get_type_chart())


# --- Auth: hasher, user repo, session store, current-user (ADR-039) --------
#
# Three small providers, each behind its own seam: a bcrypt swap, a Redis-backed
# session store, or an OAuth/OIDC `get_current_user` are all one-line changes
# here — the routers and business code see the abstract role and stay unchanged.


def get_password_hasher() -> Argon2PasswordHasher:
    """Provider for password hashing. Swap to a different `*PasswordHasher` with
    the same two-method shape (`hash`, `verify`) to change algorithm."""
    return Argon2PasswordHasher()


def get_auth_repo(
    session: AsyncSession = Depends(get_session),
) -> SqlAuthRepository:
    """Provider for the user repo (signup / lookup by email or id)."""
    return SqlAuthRepository(session)


def get_session_store(
    session: AsyncSession = Depends(get_session),
) -> DbSessionStore:
    """Provider for the session store. Three-method interface (`create`, `lookup`,
    `revoke`) intentionally narrow so a Redis-backed store is a drop-in swap."""
    return DbSessionStore(session)


async def get_current_user(
    request: Request,
    store: DbSessionStore = Depends(get_session_store),
) -> User:
    """Resolve the current user from the session cookie, or raise 401.

    This is the seam to swap when introducing OAuth/OIDC — a different provider
    returns a `User` from a different credential source, and every router that
    already takes `user: User = Depends(get_current_user)` keeps working. Catalog
    endpoints (`GET /api/pokemon`, `/healthz`) deliberately do NOT depend on this
    so they remain public.
    """
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await store.lookup(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
