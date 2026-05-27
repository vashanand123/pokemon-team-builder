"""SQLAlchemy ORM rows — the *persistence* shape of every entity.

Every class here is suffixed `*Row` (ADR-038) so the file you're reading is
unambiguously the persistence layer: the rest of the app sees the matching
business dataclass (`app.business.pokemon.Pokemon`, etc.), and adapters
translate between the two. Table names are unchanged so no schema migration is
required.

Computed views (`types`, `stats`, `snapshot`, `apply_normalized`,
`from_normalized`) live on `PokemonRow` because the change-scan orchestrator
operates on rows directly when applying upstream updates — keeping those
helpers on the row avoids ferrying every field through a translation step on a
write that's already a single-row mutation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_STAT_FIELDS = ("hp", "attack", "defense", "special_attack", "special_defense", "speed")


def _uuid() -> str:
    """Return a fresh random UUID as a hex string — default factory for surrogate
    primary keys (users, teams, counter_teams, change_events)."""
    return str(uuid.uuid4())


def _now() -> datetime:
    """Return the current UTC time — default factory for `created_at`/`updated_at`."""
    return datetime.now(timezone.utc)


class UserRow(Base):
    """A real user with a chosen **username** + Argon2id password hash (ADR-039/041).

    Replaces the Phase-1 anonymous-cookie identity: every user must sign up before
    they can create anything. Username (not email) is deliberate — the project is a
    take-home demo where reviewers want to spin up multiple throwaway accounts on
    the spot without owning N inboxes (ADR-041). `is_admin` is a placeholder for a
    future admin-page gate (the `/admin/*` endpoints stay open for dev convenience
    for now, per the plan's open-scope notes).
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    is_admin: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    teams: Mapped[list[TeamRow]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[SessionRow]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class PokemonRow(Base):
    """Normalized catalog row: one column per attribute we filter or sort on.

    `types` / `stats` / `snapshot` are read-only views so callers and adapters
    keep a convenient shape while storage stays relational (DECISIONS.md ADR-018).
    """

    __tablename__ = "pokemon"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # PokeAPI id
    name: Mapped[str] = mapped_column(String, index=True)
    type1: Mapped[str] = mapped_column(String, index=True)
    type2: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    hp: Mapped[int] = mapped_column(Integer)
    attack: Mapped[int] = mapped_column(Integer)
    defense: Mapped[int] = mapped_column(Integer)
    special_attack: Mapped[int] = mapped_column(Integer)
    special_defense: Mapped[int] = mapped_column(Integer)
    speed: Mapped[int] = mapped_column(Integer)
    sprite_url: Mapped[str | None] = mapped_column(String, nullable=True)
    is_legendary: Mapped[bool] = mapped_column(default=False)
    is_mythical: Mapped[bool] = mapped_column(default=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    @property
    def types(self) -> list[str]:
        """The 1-or-2-element list of types, reconstructed from `type1` / `type2`.
        Computed (not stored) so adapters and the change-scan see the convenient
        list shape while storage stays relational + indexable (ADR-018)."""
        return [self.type1] + ([self.type2] if self.type2 else [])

    @property
    def stats(self) -> dict[str, int]:
        """The six stats as a dict (`{"hp": 78, "attack": 84, ...}`), reconstructed
        from the individual columns. Used by the change-scan snapshot diff."""
        return {field: getattr(self, field) for field in _STAT_FIELDS}

    @property
    def base_stat_total(self) -> int:
        """Sum of the six base stats. Same value as business `Pokemon.bst` — kept
        here too because the catalog list's "total" sort computes the same number
        in SQL."""
        return sum(getattr(self, field) for field in _STAT_FIELDS)

    @property
    def snapshot(self) -> dict:
        """Normalized view compared by the change detector."""
        return {
            "id": self.id,
            "name": self.name,
            "types": self.types,
            "stats": self.stats,
            "sprite_url": self.sprite_url,
        }

    def apply_normalized(self, doc: dict) -> None:
        """Set columns from a normalized doc (see app.business.snapshots).

        Used by the change-scan when upstream has changed a Pokémon and we want
        to record the new state in place.
        """
        self.name = doc["name"]
        types = doc["types"]
        self.type1 = types[0]
        self.type2 = types[1] if len(types) > 1 else None
        for field in _STAT_FIELDS:
            setattr(self, field, doc["stats"][field])
        self.sprite_url = doc.get("sprite_url")
        self.is_legendary = doc.get("is_legendary", False)
        self.is_mythical = doc.get("is_mythical", False)

    @classmethod
    def from_normalized(cls, doc: dict) -> PokemonRow:
        """Construct a fresh `PokemonRow` from a normalized doc (the dict produced
        by `app.business.snapshots.normalize_pokemon`). The natural id from the doc
        becomes the primary key; all other columns are set via `apply_normalized`.
        Used by the seed and the ADR-036 discovery pass."""
        pokemon = cls(id=doc["id"])
        pokemon.apply_normalized(doc)
        return pokemon


class TeamRow(Base):
    """A user's team — up to 6 Pokémon with a name. Owned by exactly one user
    (cascade on user delete). Hard-deleted (no soft-delete column in v1)."""

    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    user: Mapped[UserRow] = relationship(back_populates="teams")
    members: Mapped[list[TeamMemberRow]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan",
        order_by="TeamMemberRow.slot",
    )
    # Saved counter teams generated against this team; deleted with it.
    counter_teams: Mapped[list[CounterTeamRow]] = relationship(
        cascade="all, delete-orphan"
    )


class TeamMemberRow(Base):
    """One slot in a team. Primary key is the composite `(team_id, slot)` — so the
    *database itself* forbids two members in the same slot (no application check
    needed), and `slot` (0..5) doubles as the display order (no separate position
    column to keep in sync)."""

    __tablename__ = "team_members"

    team_id: Mapped[str] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    slot: Mapped[int] = mapped_column(Integer, primary_key=True)  # 0..5, encodes order
    pokemon_id: Mapped[int] = mapped_column(ForeignKey("pokemon.id"))

    team: Mapped[TeamRow] = relationship(back_populates="members")
    pokemon: Mapped[PokemonRow] = relationship()


class CounterTeamRow(Base):
    """A saved counter team generated against a source team.

    A counter team is a *snapshot of an algorithm result*, not an editable team: it is
    never reordered or queried relationally, only saved and re-displayed. So the members
    are an ordered JSON list of Pokémon ids and the score breakdown is JSON — the same
    "JSON for document-shaped data" call as ChangeEventRow.diff (DECISIONS.md ADR-018/025).
    """

    __tablename__ = "counter_teams"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    source_team_id: Mapped[str] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), index=True
    )
    mode: Mapped[str] = mapped_column(String)  # legacy column (modes removed; ADR-036)
    member_ids: Mapped[list[int]] = mapped_column(JSON)  # ordered Pokémon ids
    score: Mapped[dict] = mapped_column(JSON)  # cached ScoreBreakdown
    team_bst: Mapped[int] = mapped_column(Integer)
    opponent_bst: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )


class ChangeEventRow(Base):
    """The audit log row written when the scan detects a Pokémon's data changed
    upstream. `diff` is JSON (variable-shape: `{field: {"old": ..., "new": ...}}`) —
    deliberate JSON-over-table call, same judgment as `counter_teams.member_ids`
    (ADR-018). Per-user alerts are computed by joining recent events to the user's
    team members on demand; there is no `alerts` table."""

    __tablename__ = "change_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    pokemon_id: Mapped[int] = mapped_column(ForeignKey("pokemon.id"), index=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )
    # Variable-shape audit payload {field: {"old": ..., "new": ...}} — genuinely
    # document-like, so JSON is the right tool here, not a relational table (ADR-018).
    diff: Mapped[dict] = mapped_column(JSON)

    pokemon: Mapped[PokemonRow] = relationship()


class SessionRow(Base):
    """Opaque server-side session (ADR-039). The PK `id` *is* the session token
    set on the user's cookie — a 256-bit random hex string from
    `business.auth.new_session_token`. Storing the token directly (rather than a
    JWT-style signed payload) lets us revoke individual sessions by deleting / null-
    timestamping a row; lookup is a single index hit.

    Held server-side: a stolen cookie can't be re-keyed and we can force-logout a
    user by setting `revoked_at`. The bearer-token trust model is the same as the
    Phase-1 cookie identity (the token is what proves who you are); the upgrade
    is that we know the row exists, who owns it, and can kill it.
    """

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # the token itself
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[UserRow] = relationship(back_populates="sessions")
