"""Unit tests for the loaded 18×18 type-effectiveness chart."""

import pytest

from app.business.type_chart import get_type_chart

pytestmark = pytest.mark.unit


def test_real_type_chart_known_relations():
    c = get_type_chart()
    assert c.multiplier("fire", "grass") == 2.0
    assert c.multiplier("fire", "water") == 0.5
    assert c.multiplier("electric", "ground") == 0.0  # immunity
    assert c.multiplier("normal", "ghost") == 0.0
    assert c.effectiveness("fire", ("grass", "steel")) == 4.0  # double up
    assert c.effectiveness("ground", ("flying",)) == 0.0


def test_unknown_pair_defaults_to_neutral():
    """Defensive default — a typo'd type name returns 1.0 instead of crashing
    the solver. Lets the change-scan add new types without immediate breakage."""
    c = get_type_chart()
    assert c.multiplier("nonexistent", "fire") == 1.0
    assert c.multiplier("fire", "nonexistent") == 1.0
