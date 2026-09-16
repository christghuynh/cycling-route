import pytest

from app.services.route_processing import calculate_elevation_gain


def test_sums_positive_changes_between_consecutive_samples() -> None:
    assert calculate_elevation_gain([100, 105, 103, 110]) == pytest.approx(12)


def test_is_not_max_minus_min() -> None:
    # max - min would be 20; the route actually climbs 20 twice.
    assert calculate_elevation_gain([100, 120, 100, 120]) == pytest.approx(40)


@pytest.mark.parametrize("elevations", [[], [250.0]])
def test_fewer_than_two_samples_has_no_gain(elevations: list[float]) -> None:
    assert calculate_elevation_gain(elevations) == 0


def test_descent_only_has_no_gain() -> None:
    assert calculate_elevation_gain([300, 280, 250, 200]) == 0


def test_flat_route_has_no_gain() -> None:
    assert calculate_elevation_gain([150, 150, 150]) == 0


def test_zero_threshold_matches_sum_of_positive_differences() -> None:
    elevations = [100, 101, 100, 102, 101, 104, 99, 99.5]
    expected = sum(max(b - a, 0) for a, b in zip(elevations, elevations[1:], strict=False))
    assert calculate_elevation_gain(elevations, noise_threshold_m=0) == pytest.approx(expected)


def test_threshold_ignores_small_noise() -> None:
    noisy_flat = [100, 101, 100, 101.5, 100.5, 101, 100]
    assert calculate_elevation_gain(noisy_flat) > 0
    assert calculate_elevation_gain(noisy_flat, noise_threshold_m=2) == 0


def test_threshold_still_counts_gradual_climb() -> None:
    # Each step is below the threshold, but the cumulative climb is not.
    gradual = [100, 101, 102, 103, 104, 105, 106]
    assert calculate_elevation_gain(gradual, noise_threshold_m=3) == pytest.approx(6)


def test_climb_after_dip_is_measured_from_bottom_of_dip() -> None:
    assert calculate_elevation_gain([104, 100, 99, 104], noise_threshold_m=3) == pytest.approx(5)


def test_threshold_keeps_spec_example_intact() -> None:
    assert calculate_elevation_gain([100, 105, 103, 110], noise_threshold_m=3) == pytest.approx(12)


def test_negative_threshold_is_rejected() -> None:
    with pytest.raises(ValueError):
        calculate_elevation_gain([1, 2], noise_threshold_m=-1)
