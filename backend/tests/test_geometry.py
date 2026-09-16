import pytest

from app.domain import Coordinate
from app.services.geometry import decode_polyline, haversine_m, path_length_m, resample_path
from tests.factories import encode_polyline


def test_decode_polyline_reference_example() -> None:
    # Example from Google's encoded polyline algorithm documentation.
    decoded = decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
    assert decoded.coordinates == [
        Coordinate(38.5, -120.2),
        Coordinate(40.7, -120.95),
        Coordinate(43.252, -126.453),
    ]
    assert decoded.elevations is None


def test_decode_polyline_round_trips_with_encoder() -> None:
    points = [(43.46431, -80.52041), (43.36161, -80.31441)]
    decoded = decode_polyline(encode_polyline(points))
    assert [(c.lat, c.lon) for c in decoded.coordinates] == points


def test_decode_polyline_with_elevation() -> None:
    points = [(43.46431, -80.52041), (43.46, -80.52), (43.36161, -80.31441)]
    elevations = [331.5, 328.25, 302.0]
    decoded = decode_polyline(encode_polyline(points, elevations), with_elevation=True)
    assert [(c.lat, c.lon) for c in decoded.coordinates] == points
    assert decoded.elevations == elevations


def test_decode_truncated_polyline_raises() -> None:
    with pytest.raises(ValueError):
        decode_polyline("_p~iF~ps|U_")


def test_haversine_one_degree_of_latitude() -> None:
    assert haversine_m(Coordinate(0, 0), Coordinate(1, 0)) == pytest.approx(111_195, rel=1e-3)


def test_haversine_same_point_is_zero() -> None:
    point = Coordinate(43.46, -80.52)
    assert haversine_m(point, point) == 0


def test_haversine_waterloo_to_cambridge() -> None:
    distance = haversine_m(Coordinate(43.4643, -80.5204), Coordinate(43.3616, -80.3144))
    assert distance == pytest.approx(19_900, rel=0.02)


def test_path_length_sums_segments() -> None:
    path = [Coordinate(0, 0), Coordinate(1, 0), Coordinate(2, 0)]
    assert path_length_m(path) == pytest.approx(2 * 111_195, rel=1e-3)


def test_path_length_of_single_point_is_zero() -> None:
    assert path_length_m([Coordinate(0, 0)]) == 0


def test_resample_uses_requested_spacing_and_keeps_endpoints() -> None:
    path = [Coordinate(0, 0), Coordinate(0.01, 0)]  # ~1112 m
    samples = resample_path(path, spacing_m=100, max_samples=1000)

    assert len(samples) == 13
    assert samples[0] == (0.0, path[0])
    assert samples[-1][1] == path[-1]
    gaps = [b[0] - a[0] for a, b in zip(samples, samples[1:], strict=False)]
    assert max(gaps) <= 100
    # Interpolated points lie on the path at the stated distance.
    distance, point = samples[5]
    assert haversine_m(path[0], point) == pytest.approx(distance, rel=1e-6)


def test_resample_respects_max_samples() -> None:
    path = [Coordinate(0, 0), Coordinate(0.5, 0), Coordinate(1, 0)]
    assert len(resample_path(path, spacing_m=10, max_samples=50)) == 50


def test_resample_handles_multi_segment_paths() -> None:
    path = [Coordinate(0, 0), Coordinate(0.001, 0), Coordinate(0.001, 0.001), Coordinate(0, 0.001)]
    samples = resample_path(path, spacing_m=20, max_samples=500)
    distances = [d for d, _ in samples]
    assert distances == sorted(distances)
    assert distances[-1] == pytest.approx(path_length_m(path))


def test_resample_degenerate_paths() -> None:
    assert resample_path([], 100, 10) == []
    single = [Coordinate(1, 1)]
    assert resample_path(single, 100, 10) == [(0.0, single[0])]
