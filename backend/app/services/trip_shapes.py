"""Waypoint generation for target-distance rides.

A router only knows how to connect waypoints, so to get "a 30 km ride from home" we choose via
points that make the ride roughly the right length, then let the router follow real roads and
trails between them.

Shape: a circle that passes through the start, with its centre pushed out in a chosen compass
direction. Via points are spaced clockwise around that circle, and the ride finishes at the
destination (the start again, for a loop). Clockwise loops mean mostly right turns in
right-hand-traffic countries, which avoids waiting to turn across traffic.

The circle radius is solved so the straight-line length of start -> via points -> finish matches
a target; routed distance is longer than straight-line distance, so callers divide the desired
ride distance by a road factor and refine it after seeing the first routed result.
"""

import math

from app.domain import Coordinate
from app.services.geometry import LocalProjection, haversine_m, path_length_m

MAX_VIA_POINTS = 4
# Straight-line length must land within this fraction of the requested length.
SOLVE_TOLERANCE = 0.02


def arc_waypoints(
    start: Coordinate, finish: Coordinate, bearing_deg: float, radius_m: float
) -> list[Coordinate]:
    """Full waypoint list (start, via points..., finish) for one circle."""
    projection = LocalProjection(start)
    bearing = math.radians(bearing_deg)
    # Compass bearing: 0 = north (+y), 90 = east (+x).
    cx, cy = radius_m * math.sin(bearing), radius_m * math.cos(bearing)
    fx, fy = projection.to_xy(finish)

    start_angle = math.atan2(-cy, -cx)
    finish_angle = math.atan2(fy - cy, fx - cx)
    # Travel from the start to the circle point nearest the finish, always passing the far side
    # of the circle so the ride grows smoothly with the radius. Clockwise (decreasing angle) is
    # used whenever that route passes the far side; otherwise go counter-clockwise.
    clockwise_sweep = (start_angle - finish_angle) % (2 * math.pi)
    if clockwise_sweep < 1e-3:
        clockwise_sweep = 2 * math.pi
    sweep = -clockwise_sweep if clockwise_sweep >= math.pi else 2 * math.pi - clockwise_sweep

    step = 2 * math.pi / (MAX_VIA_POINTS + 1)
    count = max(1, min(MAX_VIA_POINTS, int(abs(sweep) / step)))
    vias = [
        projection.to_coordinate(
            cx + radius_m * math.cos(start_angle + sweep * i / (count + 1)),
            cy + radius_m * math.sin(start_angle + sweep * i / (count + 1)),
        )
        for i in range(1, count + 1)
    ]
    return [start, *vias, finish]


def solve_waypoints(
    start: Coordinate, finish: Coordinate, bearing_deg: float, straight_length_m: float
) -> list[Coordinate] | None:
    """Waypoints whose straight-line path length is about `straight_length_m`.

    Returns None when no circle in this direction fits, e.g. the finish is already further away
    than the requested length.
    """

    def length(radius: float) -> float:
        return path_length_m(arc_waypoints(start, finish, bearing_deg, radius))

    low, high = 1.0, straight_length_m
    if length(low) >= straight_length_m or length(high) < straight_length_m:
        return None
    for _ in range(50):
        mid = (low + high) / 2
        if length(mid) < straight_length_m:
            low = mid
        else:
            high = mid
    waypoints = arc_waypoints(start, finish, bearing_deg, high)
    if abs(path_length_m(waypoints) / straight_length_m - 1) > SOLVE_TOLERANCE:
        return None
    return waypoints


def initial_bearing_deg(a: Coordinate, b: Coordinate) -> float:
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    d_lon = math.radians(b.lon - a.lon)
    x = math.sin(d_lon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
    return math.degrees(math.atan2(x, y)) % 360


def candidate_bearings(start: Coordinate, finish: Coordinate, count: int) -> list[float]:
    """Evenly spread directions to try. For A-to-B rides they are aligned with the trip axis."""
    offset = 0.0 if haversine_m(start, finish) < 50 else initial_bearing_deg(start, finish)
    return [(offset + i * 360 / count) % 360 for i in range(count)]
