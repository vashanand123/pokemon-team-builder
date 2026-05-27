"""All Pydantic request/response schemas — the API wire contract.

One module for the whole app's DTOs; at this size per-resource files were just
ceremony. Grouped by resource below. `from_attributes=True` lets a model read
straight off an ORM row (including its computed @property views).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.business.auth import (
    MAX_USERNAME_LENGTH,
    MIN_PASSWORD_LENGTH,
    MIN_USERNAME_LENGTH,
)
from app.core.config import MAX_TEAM_MEMBERS

# --- Pokémon ---------------------------------------------------------------


class PokemonOut(BaseModel):
    """Wire shape for one Pokémon — what `GET /api/pokemon/{id}` returns and what
    nests inside a `TeamMemberOut`. `from_attributes=True` lets Pydantic read fields
    off the ORM row (including the computed `types`/`stats` views — they don't have
    to be real columns)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    types: list[str]
    stats: dict[str, int]
    sprite_url: str | None = None
    is_legendary: bool = False
    is_mythical: bool = False


class PokemonListOut(BaseModel):
    """Wire shape for the paginated catalog response — `items` are the rows on this
    page, `total` is the total match count *before* limit/offset (so the UI can
    render "X Pokémon" independent of pagination)."""

    items: list[PokemonOut]
    total: int


# --- Teams -----------------------------------------------------------------


class TeamMemberOut(BaseModel):
    """One slot in a team's response — its `slot` (0..5, encodes order) plus the
    full nested `PokemonOut`."""

    model_config = ConfigDict(from_attributes=True)

    slot: int
    pokemon: PokemonOut


class TeamOut(BaseModel):
    """Wire shape for a team. Deliberately omits `user_id` — there's no need to send
    the owner UUID back; if the API returns a team, the requester owns it (cross-user
    requests get 404'd by the repo, never reaching the response)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    members: list[TeamMemberOut]
    created_at: datetime
    updated_at: datetime


class TeamCreate(BaseModel):
    """Request body for `POST /api/teams`. `member_ids` are PokéAPI ids in slot order
    (position 0 = first slot, …). The team-size cap (`MAX_TEAM_MEMBERS = 6`) is enforced
    here at the Pydantic boundary, so > 6 members → automatic 422."""

    name: str = Field(min_length=1, max_length=60)
    # Ordered list of Pokémon ids; slot = position.
    member_ids: list[int] = Field(default_factory=list, max_length=MAX_TEAM_MEMBERS)

    @field_validator("name")
    @classmethod
    def _strip_and_require_nonblank(cls, v: str) -> str:
        """Trim whitespace and reject names that collapse to empty — Pydantic's
        `min_length=1` alone lets `'   '` through, which would persist as a
        visually-empty team name."""
        v = v.strip()
        if not v:
            raise ValueError("Team name cannot be blank")
        return v


class TeamUpdate(BaseModel):
    """Request body for `PUT /api/teams/{id}`. Both fields are optional — what's
    omitted is left alone. Sending `member_ids: []` clears the team; sending no
    `member_ids` leaves the current member list intact."""

    name: str | None = Field(default=None, min_length=1, max_length=60)
    member_ids: list[int] | None = Field(default=None, max_length=MAX_TEAM_MEMBERS)

    @field_validator("name")
    @classmethod
    def _strip_and_require_nonblank(cls, v: str | None) -> str | None:
        """Same trim-and-reject-blank guard as `TeamCreate.name`. `None` (the
        "don't change the name" signal) passes through untouched."""
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("Team name cannot be blank")
        return v


# --- Counters --------------------------------------------------------------


class GenerateCounterRequest(BaseModel):
    """Request body for `POST /api/teams/{id}/counters/generate`. `include_forms`
    opens the candidate pool to alternate forms (megas, primals, Eternamax, ...) —
    off by default so suggestions are sensible base species (ADR-015/029)."""

    include_forms: bool = False  # allow megas/primals/etc. (else base species only)


class SaveCounterRequest(BaseModel):
    """Persist a previously generated counter: just the chosen members."""

    member_ids: list[int] = Field(min_length=1, max_length=MAX_TEAM_MEMBERS)


class ScoreBreakdown(BaseModel):
    """The counter's score, per the sbgames-2020 fitness (CP × type-effectiveness).

    `extra="ignore"` lets counters saved under the previous (5-axis) objective still
    deserialize — their unknown keys are dropped and the new fields default to 0.
    """

    model_config = ConfigDict(extra="ignore")

    fitness: float = 0.0  # the paper's summed battle value (higher = better; unbounded)
    win_rate: float = 0.0  # fraction of head-to-head pairings the counter wins (0..1)
    team_cp: float = 0.0  # total Combat Power of the counter team
    opponent_cp: float = 0.0  # total Combat Power of the team being countered


class CounterPreviewOut(BaseModel):
    """An unsaved, freshly generated counter team (no id — not persisted yet)."""

    team: list[PokemonOut]
    score: ScoreBreakdown
    team_bst: int
    opponent_bst: int


class SavedCounterOut(BaseModel):
    """A persisted counter team, tied to the source team it counters."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    source_team_id: str
    team: list[PokemonOut]
    score: ScoreBreakdown
    team_bst: int
    opponent_bst: int
    created_at: datetime


# --- Alerts ----------------------------------------------------------------


class AlertOut(BaseModel):
    """Wire shape for one change-alert — the `Pokemon` that changed, when the change
    was detected upstream, and the structured `diff` (`{field: {"old": ..., "new": ...}}`)
    showing exactly what's different vs the stored snapshot."""

    model_config = ConfigDict(from_attributes=True)

    pokemon: PokemonOut
    detected_at: datetime
    diff: dict


# --- Auth (ADR-039/041) ----------------------------------------------------


class SignupRequest(BaseModel):
    """Body for `POST /api/auth/signup`. Username (not email) is deliberate (ADR-041)
    — the project is a demo where reviewers want to spin up multiple accounts on
    the spot. The frontend has a confirm-password field for typo defense; the
    backend only takes the single chosen password (matching is purely a UX check)."""

    username: str = Field(min_length=MIN_USERNAME_LENGTH, max_length=MAX_USERNAME_LENGTH)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)


class LoginRequest(BaseModel):
    """Body for `POST /api/auth/login`. No password-length floor here — older
    passwords might exist if MIN_PASSWORD_LENGTH ever changed — we just verify."""

    username: str = Field(min_length=1, max_length=MAX_USERNAME_LENGTH)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    """Wire shape for the current user — `GET /api/auth/me`. No password hash, no
    sessions list; just what the UI needs to render."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    created_at: datetime
