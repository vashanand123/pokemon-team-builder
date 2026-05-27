from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.models import Base  # noqa: F401 — importing models registers them on Base

engine = create_async_engine(settings.database_url, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


if engine.url.get_backend_name() == "sqlite":

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # noqa: ANN001
        """Apply the three SQLite-only PRAGMAs (ADR-013) on EVERY new connection:

        - `foreign_keys=ON`: SQLite ignores FK constraints by default, so our `ON DELETE
          CASCADE` rules would silently do nothing without this.
        - `journal_mode=WAL`: Write-Ahead Logging — lets many readers work while one
          writer appends, instead of locking the whole file. The reason the change-scan
          can run while requests serve.
        - `busy_timeout=5000`: if two writers do collide, wait up to 5 s for the lock
          instead of instantly erroring "database is locked".

        Skipped on Postgres (the outer `if engine.url.get_backend_name() == "sqlite"`
        guard) — those concerns are handled natively there.
        """
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()


async def init_db() -> None:
    """Create tables from ORM metadata.

    Adequate for a fixture-backed SQLite database; production would use Alembic
    migrations instead (see DECISIONS.md ADR-003).
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a scoped async session."""
    async with SessionLocal() as session:
        yield session
