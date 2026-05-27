import json
from pathlib import Path

# backend/data/type_chart.json — the derived 18×18 effectiveness matrix, and the single
# source of truth for the canonical battle types (its keys). Built from PokéAPI /type by
# app.db.seed; there is intentionally no hardcoded type list (see DECISIONS.md ADR-007).
# `parents[2]` walks app/business/type_chart.py → app/business/ → app/ → backend/.
_DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "type_chart.json"


class TypeChart:
    """Type-effectiveness lookup. `matrix[attacking][defending]` is a multiplier."""

    def __init__(self, matrix: dict[str, dict[str, float]]) -> None:
        """Wrap the loaded `attacking_type → {defending_type: multiplier}` matrix.
        Built once by `get_type_chart()` from `data/type_chart.json`."""
        self._m = matrix

    @property
    def types(self) -> list[str]:
        """The canonical battle types — the matrix's attacking-type keys.

        Derived from the loaded chart so the type set lives in exactly one place
        (the JSON), never duplicated as a hardcoded list in code.
        """
        return list(self._m.keys())

    def multiplier(self, attacking: str, defending: str) -> float:
        """One-vs-one type lookup: `chart[attacking][defending]`. Defaults to **1.0**
        (neutral) for any pair not in the matrix — defensive default so a typo in
        type data doesn't blow up the solver."""
        return self._m.get(attacking, {}).get(defending, 1.0)

    def effectiveness(self, attacking: str, defender_types) -> float:
        """Multiplier of an `attacking`-type move against a (1- or 2-type) defender."""
        result = 1.0
        for d in defender_types:
            result *= self.multiplier(attacking, d)
        return result


_chart: TypeChart | None = None


def get_type_chart() -> TypeChart:
    """Lazily load the derived type chart (cached for the process)."""
    global _chart
    if _chart is None:
        matrix = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
        _chart = TypeChart(matrix)
    return _chart
