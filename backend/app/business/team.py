"""Business `Team` + `TeamMember` — what the team endpoints return.

Adapters (`SqlTeamRepository`) translate `TeamRow`/`TeamMemberRow` into these
dataclasses. The wire schemas (`TeamOut`, `TeamMemberOut`) read attributes off
these via Pydantic's `from_attributes=True`, so the field names here are the
wire contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.business.pokemon import Pokemon


@dataclass(frozen=True)
class TeamMember:
    """One slot in a team — slot index (0..5, doubles as display order) plus the
    full nested `Pokemon`. `TeamMemberOut` reads these two attributes."""

    slot: int
    pokemon: Pokemon


@dataclass(frozen=True)
class Team:
    """A user's team — the response shape for `GET /api/teams/{id}`.

    `user_id` is held server-side for permission checks and is intentionally NOT
    in the wire schema (`TeamOut`) — if the API returns a team, the requester
    owns it; cross-user requests are 404'd at the repo before reaching this point.
    """

    id: str
    name: str
    members: tuple[TeamMember, ...]
    created_at: datetime
    updated_at: datetime
    user_id: str
