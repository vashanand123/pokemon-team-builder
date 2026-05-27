from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.admin import router as admin_router
from app.api.alerts import router as alerts_router
from app.api.auth import router as auth_router
from app.api.counter import router as counter_router
from app.api.pokemon import router as pokemon_router
from app.api.teams import router as teams_router
from app.core.config import settings
from app.db.seed import load_fixture_into_db
from app.db.session import SessionLocal, init_db
from app.scheduler import shutdown_scheduler, start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hook FastAPI runs around the app's request-serving life.

    Startup (before `yield`): create tables from the ORM metadata (`create_all`), then
    seed the catalog from the committed fixture if the `pokemon` table is empty
    (idempotent — re-runs are no-ops), then start the in-process hourly scan unless
    tests have disabled it.
    Shutdown (after `yield`): stop the scheduler cleanly.
    """
    # Create tables, then load the committed fixture into SQLite if empty.
    await init_db()
    async with SessionLocal() as session:
        inserted = await load_fixture_into_db(session)
        if inserted:
            print(f"Seeded {inserted} Pokémon from fixture")
    if settings.scheduler_enabled:
        start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="Pokemon Team Builder", version="0.1.0", lifespan=lifespan)


@app.get("/healthz", tags=["health"])
async def healthz() -> dict[str, str]:
    """Liveness probe — returns `{"status": "ok"}` so Docker's healthcheck (and any
    external uptime monitor) can confirm the app is up and the event loop is running."""
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(pokemon_router)
app.include_router(teams_router)
app.include_router(counter_router)
app.include_router(alerts_router)
app.include_router(admin_router)
