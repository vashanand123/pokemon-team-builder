"""Business layer — what the rest of the app passes around.

This package holds the *business objects* (frozen dataclasses with the shape the
API serves) and the *pure logic* that operates on them (the GA strategy, type
chart, snapshot diff, change-scan orchestrator).

Hard rule: **nothing in here imports from `app.db`.** Adapters are the only
boundary that knows about ORM rows; this package only sees the business shapes
they translate to. That single import rule is what keeps the seams clean (and
what makes a future swap of SQLite → Postgres a one-line change in
`app/api/deps.py`, not a sweep through business code).
"""

from app.business.alert import Alert
from app.business.counter_team import CounterTeam
from app.business.pokemon import Pokemon
from app.business.team import Team, TeamMember
from app.business.user import User

__all__ = ["Alert", "CounterTeam", "Pokemon", "Team", "TeamMember", "User"]
