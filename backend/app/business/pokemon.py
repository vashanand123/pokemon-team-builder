"""Business `Pokemon` — what the API returns and what the GA operates on.

This is the dataclass the rest of the app passes around. It replaces the two
shapes the project used to carry separately (the ORM `Pokemon` row and the
solver-only `Mon`) — see DECISIONS.md ADR-037/038. Adapters build it from a
`PokemonRow`; nothing else in the app should know `PokemonRow` exists.

Computed views (`stats`, `bst`, `cp`, `snapshot`) live here so business code
never needs to compute them on the ORM side.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Combat Power coefficients from the sbgames-2020 paper's eq. (2). C is the level
# constant (0.7903 = the max-level value); IVs (Attack/Defense/Stamina individual
# values) are set to their maximum (15) — both exactly the paper's choices, so CP
# ranks Pokémon by raw power.
_CP_LEVEL_C = 0.7903
_MAX_IV = 15


@dataclass(frozen=True)
class Pokemon:
    """One Pokémon as the application sees it. Frozen so it's safe to pass around
    without defensive copies; the GA needs hashable members so type-diversity
    sets and exclusion sets stay simple."""

    id: int
    name: str
    types: tuple[str, ...]
    hp: int
    attack: int
    defense: int
    special_attack: int
    special_defense: int
    speed: int
    sprite_url: str | None = None
    is_legendary: bool = False
    is_mythical: bool = False

    @property
    def stats(self) -> dict[str, int]:
        """The six base stats as a dict (`{"hp": 78, "attack": 84, ...}`).
        Convenient shape for the API serializer and the change-scan diff."""
        return {
            "hp": self.hp,
            "attack": self.attack,
            "defense": self.defense,
            "special_attack": self.special_attack,
            "special_defense": self.special_defense,
            "speed": self.speed,
        }

    @property
    def bst(self) -> int:
        """Base Stat Total — the sum of all six base stats. A rough "raw
        strength" proxy; used as the tiebreaker in `autofill`."""
        return (
            self.hp
            + self.attack
            + self.defense
            + self.special_attack
            + self.special_defense
            + self.speed
        )

    @property
    def cp(self) -> float:
        """Combat Power, paper eq. (2):

            CP = (Attack + Aiv) · √(Def + Div) · √(Stam + Siv) · C² / 10

        Pokémon GO has single Attack/Defense/Stamina stats; we map our
        main-series stats to them: offense = the better attacking stat,
        defense = the better wall, stamina = HP. With maximum IVs (15) and the
        max-level constant C = 0.7903.
        """
        atk = max(self.attack, self.special_attack)
        dfn = max(self.defense, self.special_defense)
        stam = self.hp
        return (
            (atk + _MAX_IV)
            * math.sqrt(dfn + _MAX_IV)
            * math.sqrt(stam + _MAX_IV)
            * _CP_LEVEL_C**2
            / 10.0
        )

    @property
    def snapshot(self) -> dict:
        """Normalized view compared by the change detector. `types` is a list
        (not the dataclass's tuple) so this equals the dict `normalize_pokemon`
        produces from a raw PokéAPI payload — equality drives the diff."""
        return {
            "id": self.id,
            "name": self.name,
            "types": list(self.types),
            "stats": self.stats,
            "sprite_url": self.sprite_url,
        }
