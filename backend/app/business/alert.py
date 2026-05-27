"""Business `Alert` — what `GET /api/me/alerts` returns.

A change-event for a Pokémon the current user teams, with the diff payload
inline so the UI doesn't have to look anything else up. Adapters translate a
`ChangeEventRow` (with its eager-loaded `PokemonRow`) into this dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.business.pokemon import Pokemon


@dataclass(frozen=True)
class Alert:
    """One change-alert. `diff` is the structured `{field: {old, new}}` payload
    `diff_snapshots` produces — variable-shape, so kept as a `dict`."""

    pokemon: Pokemon
    detected_at: datetime
    diff: dict
