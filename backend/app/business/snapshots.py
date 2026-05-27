"""Snapshot helpers: build a normalized snapshot from a raw PokéAPI payload, and
diff two snapshots.

Both are pure functions (no I/O), so they're trivially unit-testable and shared by
the seed pipeline and the change detector.
"""

# PokéAPI stat names → our snake_case keys.
STAT_KEYS = {
    "hp": "hp",
    "attack": "attack",
    "defense": "defense",
    "special-attack": "special_attack",
    "special-defense": "special_defense",
    "speed": "speed",
}

# The user-facing fields the change detector compares.
TRACKED_FIELDS = ("name", "types", "stats", "sprite_url")


def normalize_pokemon(raw: dict) -> dict:
    """Extract the 5 fields we use from a /pokemon/{id} payload.

    Returns a plain dict (also stored verbatim as the `snapshot` used for diffing).
    """
    types = [t["type"]["name"] for t in sorted(raw["types"], key=lambda t: t["slot"])]
    stats = {
        STAT_KEYS[s["stat"]["name"]]: s["base_stat"]
        for s in raw["stats"]
        if s["stat"]["name"] in STAT_KEYS
    }
    sprite_url = (raw.get("sprites") or {}).get("front_default")
    return {
        "id": raw["id"],
        "name": raw["name"],
        "types": types,
        "stats": stats,
        "sprite_url": sprite_url,
    }


def diff_snapshots(old: dict, new: dict) -> dict:
    """Structured diff of the user-facing fields only.

    Ignoring everything else means irrelevant PokéAPI churn (cries, game indices,
    move lists, ...) never produces a noisy alert (see DECISIONS.md).
    """
    diff: dict[str, dict] = {}
    for field in TRACKED_FIELDS:
        if old.get(field) != new.get(field):
            diff[field] = {"old": old.get(field), "new": new.get(field)}
    return diff
