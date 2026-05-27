"""Shared fixtures (ADR-040).

Two-axis test split:
  * `unit/`    — pure-logic tests (no DB, no HTTP). Fast.
  * `integration/` — real DB + real router wiring via TestClient.

Both axes start from a *known* state on every test (drop+create the schema; the
integration `api_client` additionally re-seeds the Pokémon fixture via the app's
lifespan). That kills cross-test order coupling — running the suite twice in a
row gives identical results.
"""

import asyncio
import os

# Set BEFORE any app import: throwaway DB + no background scheduler.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("SCHEDULER_ENABLED", "false")

import pytest  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.models import Base  # noqa: E402,F401  — importing models registers them


# --- DB lifecycle helpers --------------------------------------------------


async def _reset_schema() -> None:
    """Drop + create every table. Cheap on an in-process SQLite DB."""
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


async def _drop_schema() -> None:
    """Drop every table — used in teardown so the file is clean for the next test."""
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


# --- Fixtures --------------------------------------------------------------


@pytest.fixture
async def session():
    """Empty DB session — for tests that talk to the ORM directly and don't need
    the catalog fixture. Drop+create on setup; drop on teardown. No data leaks
    between tests, ever.
    """
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def api_client():
    """A `TestClient` against the real app, with the DB freshly reset and
    re-seeded for this test via the app's lifespan.

    The integration tests' golden contract: every test sees the same starting
    catalog and an otherwise empty schema. Hammered into shape by:
      1. drop all tables BEFORE TestClient enters (so the lifespan reseeds);
      2. TestClient(app) triggers lifespan → `init_db` (create) +
         `load_fixture_into_db` (the committed Pokémon JSON);
      3. test runs against a known catalog and empty users/teams/sessions;
      4. drop all tables AFTER, so the next test starts clean too.
    """
    asyncio.run(_reset_schema())  # ensure empty before TestClient lifespan
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client:
        yield client
    asyncio.run(_drop_schema())
