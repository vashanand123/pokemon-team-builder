"""Business `User` — the authenticated identity routers pass around (ADR-039/041).

Adapters (`SqlAuthRepository`) translate `UserRow` into this; nothing else in
the app should know about `UserRow` or the password hash column.

Username (not email) is the identifier — see ADR-041 for the rationale.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class User:
    """One authenticated user. The wire schema (`UserOut`) reads these
    attributes via Pydantic `from_attributes=True`."""

    id: str
    username: str
    created_at: datetime
