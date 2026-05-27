"""Business `CounterTeam` — what `GET /api/teams/{id}/counters` returns.

Adapters (`SqlCounterRepository`) translate `CounterTeamRow` into this
dataclass, resolving the stored `member_ids` JSON list back to full `Pokemon`
objects via the catalog repo. The wire schema (`SavedCounterOut`) reads
attributes off this dataclass via `from_attributes=True`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.business.pokemon import Pokemon


@dataclass(frozen=True)
class CounterTeam:
    """A saved counter team for a source team.

    A counter is a *snapshot of an algorithm result*, not an editable team — so
    `team` is a fixed sequence of `Pokemon`, and `score` is the persisted
    `ScoreBreakdown` payload (kept as a dict because its shape evolved across
    ADRs; see schemas.ScoreBreakdown with `extra="ignore"`). `user_id` is
    server-side for scoping; not in the wire schema.
    """

    id: str
    source_team_id: str
    team: tuple[Pokemon, ...]
    score: dict
    team_bst: int
    opponent_bst: int
    created_at: datetime
    user_id: str
