"""Estimated safety score derived from the kinds of ways a route uses.

This is a *proxy*, not a measure of real-world safety. It knows nothing about traffic volume,
speed limits, lane widths, lighting, or collision history; it only rewards routes that spend
more of their distance on infrastructure that is typically separated from motor traffic.
"""

# Rough 0-100 rating per way type. Dedicated cycling infrastructure rates highest, busy arterial
# roads lowest. Values are deliberately simple so the resulting score is easy to explain.
WAY_TYPE_SAFETY = {
    "cycleway": 100.0,
    "path": 85.0,
    "street": 70.0,
    "track": 65.0,
    "footway": 60.0,
    "ferry": 60.0,
    "unknown": 50.0,
    "road": 45.0,
    "steps": 30.0,
    "construction": 20.0,
    "state_road": 15.0,
}

# If more than this share of the route has no way-type information, don't pretend to know.
MAX_UNKNOWN_SHARE = 0.5

SEPARATED_WAY_TYPES = ("cycleway", "path")
MAJOR_ROAD_WAY_TYPES = ("state_road", "road")


def estimate_safety_score(way_type_shares: dict[str, float]) -> float | None:
    """Distance-weighted average of way-type ratings, or `None` if there is too little data."""
    if not way_type_shares or way_type_shares.get("unknown", 0.0) > MAX_UNKNOWN_SHARE:
        return None
    total_share = sum(way_type_shares.values())
    weighted = sum(
        share * WAY_TYPE_SAFETY.get(way_type, WAY_TYPE_SAFETY["unknown"])
        for way_type, share in way_type_shares.items()
    )
    return weighted / total_share


def share_of(way_type_shares: dict[str, float], way_types: tuple[str, ...]) -> float:
    return sum(way_type_shares.get(way_type, 0.0) for way_type in way_types)
