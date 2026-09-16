import pytest

from app.domain import CandidateRoute, Coordinate
from app.services.route_processing import (
    build_route_metrics,
    calculate_repeated_share,
    calculate_way_type_shares,
    estimate_duration_min,
    route_cells,
    route_overlap,
)


def line(start: Coordinate, lat_step: float, lon_step: float, count: int) -> list[Coordinate]:
    return [Coordinate(start.lat + lat_step * i, start.lon + lon_step * i) for i in range(count)]


# --- Route metrics ----------------------------------------------------------------------------


def test_way_type_shares_are_fractions_of_total() -> None:
    shares = calculate_way_type_shares({"cycleway": 750, "road": 250, "path": 0})
    assert shares == {"cycleway": 0.75, "road": 0.25}


def test_way_type_shares_empty_when_no_distance() -> None:
    assert calculate_way_type_shares({}) == {}


def test_estimate_duration() -> None:
    assert estimate_duration_min(18, 18) == pytest.approx(60)


def test_build_metrics_uses_provider_data_and_route_elevations() -> None:
    candidate = CandidateRoute(
        geometry=[Coordinate(0, 0), Coordinate(0, 0.005), Coordinate(0, 0.01)],
        distance_m=1_500,
        duration_s=300,
        way_type_distances_m={"cycleway": 1_000, "state_road": 500},
        elevations=[100, 110, 105],
    )

    metrics = build_route_metrics(candidate, noise_threshold_m=0, default_speed_kmh=18)

    assert metrics.distance_km == 1.5
    assert metrics.duration_min == 5
    assert metrics.elevation_gain_m == 10
    assert [p.elevation_m for p in metrics.elevation_profile] == [100, 110, 105]
    assert metrics.elevation_profile[-1].distance_km == pytest.approx(1.112, rel=1e-3)
    assert metrics.way_type_shares == pytest.approx({"cycleway": 2 / 3, "state_road": 1 / 3})
    assert metrics.safety_score == pytest.approx(100 * 2 / 3 + 15 / 3)
    assert metrics.repeated_share == 0


def test_build_metrics_falls_back_when_provider_data_missing() -> None:
    candidate = CandidateRoute(
        geometry=[Coordinate(0, 0), Coordinate(0.1, 0)], distance_m=None, duration_s=None
    )
    metrics = build_route_metrics(candidate, noise_threshold_m=3, default_speed_kmh=20)

    assert metrics.distance_km == pytest.approx(11.12, rel=1e-3)
    assert metrics.duration_min == pytest.approx(metrics.distance_km * 3)
    assert metrics.elevation_gain_m is None
    assert metrics.elevation_profile == []
    assert metrics.safety_score is None


def test_elevation_profile_is_downsampled_for_long_routes() -> None:
    geometry = line(Coordinate(43, -80), 0.0001, 0, 1000)
    candidate = CandidateRoute(
        geometry=geometry, distance_m=None, duration_s=None, elevations=[300.0] * 1000
    )
    metrics = build_route_metrics(candidate, noise_threshold_m=3, default_speed_kmh=18)
    assert len(metrics.elevation_profile) <= 201
    assert metrics.elevation_profile[-1].distance_km == pytest.approx(11.1, rel=0.01)


def test_build_metrics_rejects_mismatched_elevations() -> None:
    candidate = CandidateRoute(
        geometry=[Coordinate(0, 0), Coordinate(0, 1)], distance_m=1, duration_s=1, elevations=[1]
    )
    with pytest.raises(ValueError):
        build_route_metrics(candidate, noise_threshold_m=0, default_speed_kmh=18)


# --- Backtracking and overlap -----------------------------------------------------------------


def test_clean_loop_has_little_repetition() -> None:
    origin = Coordinate(43.46, -80.52)
    square = [
        origin,
        Coordinate(43.50, -80.52),
        Coordinate(43.50, -80.46),
        Coordinate(43.46, -80.46),
        origin,
    ]
    assert calculate_repeated_share(square) < 0.02


def test_out_and_back_is_mostly_repeated() -> None:
    origin = Coordinate(43.46, -80.52)
    turnaround = Coordinate(43.52, -80.52)
    share = calculate_repeated_share([origin, turnaround, origin])
    assert share == pytest.approx(0.5, abs=0.05)


def test_route_overlap() -> None:
    a = route_cells([Coordinate(43.46, -80.52), Coordinate(43.50, -80.52)])
    b = route_cells([Coordinate(43.46, -80.52), Coordinate(43.48, -80.52)])
    c = route_cells([Coordinate(43.46, -80.40), Coordinate(43.50, -80.40)])
    assert route_overlap(a, b) == pytest.approx(1.0, abs=0.05)
    assert route_overlap(a, c) == 0
    assert route_overlap(a, set()) == 0
