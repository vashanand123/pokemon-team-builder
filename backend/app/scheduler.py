from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.adapters.pokeapi_client import HttpPokeApiClient
from app.business.changes import scan_all
from app.db.session import SessionLocal

# In-process scheduler. The job is a thin caller of the same `scan_all` orchestrator
# used by POST /admin/scan-changes — schedule and work are cleanly separated (ADR-009).
# `scan_all` runs the three passes added in ADR-036: discovery (new species), the change
# scan (now the whole catalog, not just team members), and new-type detection.
scheduler = AsyncIOScheduler()


async def _scan_job() -> None:
    """The actual work the scheduler runs each tick: open a fresh session + HTTP
    client and call the same `scan_all` orchestrator the admin endpoint uses."""
    async with SessionLocal() as session, HttpPokeApiClient() as client:
        await scan_all(session, client)


def start_scheduler() -> None:
    """Register the hourly `_scan_job` and start the scheduler. Idempotent —
    `replace_existing=True` means re-calling won't double-register. Called from
    `main.py`'s lifespan if `settings.scheduler_enabled` is true (tests disable it)."""
    if not scheduler.running:
        scheduler.add_job(
            _scan_job, "interval", hours=1, id="scan_changes", replace_existing=True
        )
        scheduler.start()


def shutdown_scheduler() -> None:
    """Stop the scheduler cleanly on app shutdown. Called from the lifespan."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
