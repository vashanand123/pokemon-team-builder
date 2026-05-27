"""SQL adapters for authentication: a user repository and a session store.

`SqlAuthRepository` is the user CRUD adapter (signup / lookup by username or id).
`DbSessionStore` is the session-CRUD adapter (create / lookup-by-token / revoke);
its three-method interface is the *seam* `get_session_store` returns, so a
Redis-backed store can swap in by changing one provider line in `api/deps.py`
without touching any router or business code (ADR-039).

Both are SQL adapters living in `adapters/` because the role of this package is
"infrastructure implementation"; both translate `UserRow` → business `User` so
business code never sees an ORM row or the password hash column.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.auth import SESSION_TTL, new_session_token
from app.business.user import User
from app.db.models import SessionRow, UserRow


def _as_utc(dt: datetime) -> datetime:
    """Return a tz-aware UTC datetime — promotes a naive value (SQLite reads) and
    leaves an already-aware value alone (Postgres reads)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _to_business(row: UserRow) -> User:
    """Translate a `UserRow` to the business `User`. Strips the password hash —
    nothing outside this adapter (and the verifier path in `api/auth.py`) ever
    sees the hash."""
    return User(
        id=row.id,
        username=row.username,
        created_at=row.created_at,
    )


def _normalize_username(username: str) -> str:
    """Lowercase + strip — usernames are case-insensitive for both storage and
    lookup so 'Alice' and 'alice' can't both exist."""
    return username.strip().lower()


class SqlAuthRepository:
    """User CRUD. The login path needs the password hash to verify against, so
    `credentials_for_username` returns it alongside the business `User` (the only
    method that does — `get_by_id` returns the hash-less business shape)."""

    def __init__(self, session: AsyncSession) -> None:
        """Hold the per-request session the FastAPI dep injected (`get_session`)."""
        self._s = session

    async def create_user(self, username: str, password_hash: str) -> User:
        """Insert a new user. The DB-level UNIQUE constraint on `username` catches
        a duplicate signup (the router translates the IntegrityError to a 409)."""
        row = UserRow(username=_normalize_username(username), password_hash=password_hash)
        self._s.add(row)
        await self._s.commit()
        await self._s.refresh(row)
        return _to_business(row)

    async def credentials_for_username(
        self, username: str
    ) -> tuple[User, str] | None:
        """Return `(user, password_hash)` for login verification, or `None` if no
        such user. Lookup is case-insensitive (stored lowercased on signup)."""
        stmt = select(UserRow).where(UserRow.username == _normalize_username(username))
        row = (await self._s.execute(stmt)).scalars().first()
        if row is None:
            return None
        return _to_business(row), row.password_hash

    async def get_by_id(self, user_id: str) -> User | None:
        """Look up a user by their surrogate id. Used by tests and any path that
        already has a verified id (the session-store path uses its own join)."""
        row = await self._s.get(UserRow, user_id)
        return _to_business(row) if row is not None else None


class DbSessionStore:
    """Server-side opaque sessions backed by the `sessions` table.

    Three-method interface (create / lookup / revoke) intentionally narrow so a
    Redis-backed store is a drop-in replacement — the provider in `api/deps.py`
    swaps the concrete class and routers stay unchanged (ADR-039).
    """

    def __init__(self, session: AsyncSession) -> None:
        """Hold the per-request session the FastAPI dep injected (`get_session`)."""
        self._s = session

    async def create(self, user_id: str) -> tuple[str, datetime]:
        """Mint a new session for the user. Returns `(token, expires_at)` — the
        token is what goes on the cookie; `expires_at` lets the router set
        `Max-Age` so the browser also forgets the cookie at the right time."""
        token = new_session_token()
        expires_at = datetime.now(timezone.utc) + SESSION_TTL
        self._s.add(
            SessionRow(id=token, user_id=user_id, expires_at=expires_at)
        )
        await self._s.commit()
        return token, expires_at

    async def lookup(self, token: str) -> User | None:
        """Return the `User` for an active session token, or `None` if the token
        is unknown, expired, or revoked. Single index hit on the `sessions` PK
        plus the eager-load of the user row.

        SQLite silently drops timezone info on store (the column is
        `DateTime(timezone=True)` for Postgres parity), so we treat any naive
        datetime read back as UTC before comparing. On Postgres `tzinfo` is
        already set, so `_as_utc` is a no-op there.
        """
        row = await self._s.get(SessionRow, token)
        if row is None:
            return None
        now = datetime.now(timezone.utc)
        if row.revoked_at is not None or _as_utc(row.expires_at) <= now:
            return None
        user_row = await self._s.get(UserRow, row.user_id)
        return _to_business(user_row) if user_row is not None else None

    async def revoke(self, token: str) -> None:
        """Mark a session revoked (idempotent — no-op if the token is unknown).
        Used by the logout endpoint; the row stays so the audit trail survives."""
        row = await self._s.get(SessionRow, token)
        if row is None or row.revoked_at is not None:
            return
        row.revoked_at = datetime.now(timezone.utc)
        await self._s.commit()
