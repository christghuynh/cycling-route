import pytest

from app.domain import Coordinate
from app.services.geometry import haversine_m, path_length_m
from app.services.trip_shapes import (
    arc_waypoints,
    candidate_bearings,
    initial_bearing_deg,
    solve_waypoints,
)

HOME = Coordinate(43.4643, -80.5204)


def test_loop_waypoints_start_and_finish_at_home() -> None:
    waypoints = arc_waypoints(HOME, HOME, bearing_deg=0, radius_m=3000)
    assert waypoints[0] == HOME
    assert waypoints[-1] == HOME
    assert len(waypoints) == 6  # start + 4 via points + finish


def test_loop_via_points_lie_on_circle_in_requested_direction() -> None:
    waypoints = arc_waypoints(HOME, HOME, bearing_deg=90, radius_m=3000)
    vias = waypoints[1:-1]
    # Every via point is east of home, and the furthest is about one diameter away.
    assert all(v.lon > HOME.lon for v in vias)
    assert max(haversine_m(HOME, v) for v in vias) == pytest.approx(6000, rel=0.1)


def test_loop_goes_clockwise() -> None:
    # Circle north of home: clockwise from the bottom means heading west (left) first.
    first_via = arc_waypoints(HOME, HOME, bearing_deg=0, radius_m=3000)[1]
    assert first_via.lon < HOME.lon


@pytest.mark.parametrize("bearing", [0, 90, 180, 270])
@pytest.mark.parametrize("length_km", [10, 30, 80])
def test_solved_loop_matches_requested_straight_line_length(
    bearing: float, length_km: float
) -> None:
    waypoints = solve_waypoints(HOME, HOME, bearing, length_km * 1000)
    assert waypoints is not None
    assert path_length_m(waypoints) == pytest.approx(length_km * 1000, rel=0.02)


def test_distance_goal_finishes_at_destination() -> None:
    finish = Coordinate(43.4800, -80.5000)  # ~2.3 km away
    waypoints = solve_waypoints(HOME, finish, bearing_deg=180, straight_length_m=20_000)
    assert waypoints is not None
    assert waypoints[0] == HOME
    assert waypoints[-1] == finish
    assert path_length_m(waypoints) == pytest.approx(20_000, rel=0.02)


def test_unreachable_length_returns_none() -> None:
    far_finish = Coordinate(43.9, -80.5)  # ~48 km away
    assert solve_waypoints(HOME, far_finish, bearing_deg=0, straight_length_m=20_000) is None


def test_bearings_for_loops_are_compass_aligned() -> None:
    assert candidate_bearings(HOME, HOME, 4) == [0, 90, 180, 270]


def test_bearings_for_trips_are_aligned_with_trip_axis() -> None:
    east = Coordinate(HOME.lat, HOME.lon + 0.05)
    bearings = candidate_bearings(HOME, east, 4)
    assert bearings[0] == pytest.approx(initial_bearing_deg(HOME, east))
    assert bearings[0] == pytest.approx(90, abs=0.5)
