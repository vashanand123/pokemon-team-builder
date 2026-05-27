"""Unit test for the seed's pure type-chart derivation."""

import pytest

from app.db.seed import fetch_type_chart

pytestmark = pytest.mark.unit


class _FakeTypeClient:
    """Minimal client exposing only the two methods fetch_type_chart needs."""

    def __init__(self, names: list[str], relations: dict[str, dict]) -> None:
        self._names = names
        self._relations = relations

    async def list_type_names(self) -> list[str]:
        return self._names

    async def get_type(self, name: str) -> dict:
        return {"damage_relations": self._relations[name]}


async def test_fetch_type_chart_excludes_non_battle_types():
    # PokéAPI's /type list includes "shadow"/"unknown" (empty relations); the derived
    # chart must drop them so its keys are exactly the real battle types.
    empty = {"double_damage_to": [], "half_damage_to": [], "no_damage_to": []}
    client = _FakeTypeClient(
        ["fire", "water", "shadow", "unknown"],
        {
            "fire": {
                "double_damage_to": [{"name": "grass"}],
                "half_damage_to": [{"name": "water"}],
                "no_damage_to": [],
            },
            "water": {
                "double_damage_to": [{"name": "fire"}],
                "half_damage_to": [],
                "no_damage_to": [],
            },
            "shadow": empty,
            "unknown": empty,
        },
    )

    matrix = await fetch_type_chart(client)

    assert set(matrix) == {"fire", "water"}  # shadow/unknown filtered out
    assert matrix["fire"]["grass"] == 2.0
    assert matrix["fire"]["water"] == 0.5
