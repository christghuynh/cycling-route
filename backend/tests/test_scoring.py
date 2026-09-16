import pytest

from app.domain import Factor
from app.services.safety import estimate_safety_score
from app.services.scoring import (
    ScoringWeights,
    distance_score,
    elevation_score,
    rank_routes,
    target_distance_score,
    weighted_overall_score,
)
from tests.factories import make_metrics

# --- Normalisation of individual components ---------------------------------------------------


@pytest.mark.parametrize(
    ("distance_km", "expected"),
    [(20.0, 100.0), (22.5, 75.0), (25.0, 50.0), (30.0, 0.0), (45.0, 0.0)],
)
def test_distance_score_relative_to_shortest(distance_km: float, expected: float) -> None:
    assert distance_score(distance_km, shortest_km=20.0) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("gain_m", "distance_km", "expected"),
    [(0, 10, 100.0), (125, 10, 50.0), (250, 10, 0.0), (1000, 10, 0.0), (50, 0, 100.0)],
)
def test_elevation_score_by_climb_per_km(
    gain_m: float, distance_km: float, expected: float
) -> None:
    assert elevation_score(gain_m, distance_km) == pytest.approx(expected)


def test_scores_stay_within_bounds() -> None:
    for km in (1, 10, 100, 1000):
        assert 0 <= distance_score(km, 1) <= 100
        assert 0 <= elevation_score(km * 10, 1) <= 100


# --- Preference weighting ---------------------------------------------------------------------


def test_weights_are_normalised_to_sum_to_one() -> None:
    weights = ScoringWeights(distance=2, elevation=1, safety=1).normalized()
    assert (weights.distance, weights.elevation, weights.safety) == pytest.approx((0.5, 0.25, 0.25))


@pytest.mark.parametrize("values", [(0, 0, 0), (-0.1, 0.5, 0.5)])
def test_invalid_weights_are_rejected(values: tuple[float, float, float]) -> None:
    with pytest.raises(ValueError):
        ScoringWeights(*values)


def test_overall_score_is_weighted_average() -> None:
    weights = ScoringWeights(distance=0.4, elevation=0.3, safety=0.3)
    components: dict[Factor, float | None] = {
        Factor.DISTANCE: 100,
        Factor.ELEVATION: 50,
        Factor.SAFETY: 80,
    }
    assert weighted_overall_score(components, weights) == pytest.approx(40 + 15 + 24)


def test_overall_score_redistributes_weight_of_missing_component() -> None:
    weights = ScoringWeights(distance=0.4, elevation=0.3, safety=0.3)
    components: dict[Factor, float | None] = {
        Factor.DISTANCE: 100,
        Factor.ELEVATION: None,
        Factor.SAFETY: 30,
    }
    assert weighted_overall_score(components, weights) == pytest.approx((40 + 9) / 0.7)


def test_overall_score_falls_back_to_equal_weights_when_available_weights_are_zero() -> None:
    weights = ScoringWeights(distance=0, elevation=1, safety=0)
    components: dict[Factor, float | None] = {
        Factor.DISTANCE: 80,
        Factor.ELEVATION: None,
        Factor.SAFETY: 60,
    }
    assert weighted_overall_score(components, weights) == pytest.approx(70)


# --- Ranking ----------------------------------------------------------------------------------


def test_routes_are_ranked_best_first() -> None:
    routes = [
        make_metrics(30, elevation_gain_m=300, safety_score=40),
        make_metrics(20, elevation_gain_m=50, safety_score=90),
        make_metrics(24, elevation_gain_m=150, safety_score=60),
    ]
    ranked, excluded = rank_routes(routes, ScoringWeights(0.4, 0.3, 0.3))

    assert excluded == set()
    assert [r.rank for r in ranked] == [1, 2, 3]
    assert [r.metrics.distance_km for r in ranked] == [20, 24, 30]
    overall = [r.scores.overall for r in ranked]
    assert overall == sorted(overall, reverse=True)


def test_preferences_change_the_ranking() -> None:
    short_hilly = make_metrics(20, elevation_gain_m=400, safety_score=50)
    long_flat = make_metrics(26, elevation_gain_m=20, safety_score=50)

    distance_first, _ = rank_routes([short_hilly, long_flat], ScoringWeights(1, 0, 0))
    elevation_first, _ = rank_routes([short_hilly, long_flat], ScoringWeights(0, 1, 0))

    assert distance_first[0].metrics is short_hilly
    assert elevation_first[0].metrics is long_flat


def test_ties_are_broken_by_shorter_distance() -> None:
    a = make_metrics(20.0, elevation_gain_m=0, safety_score=80)
    b = make_metrics(20.05, elevation_gain_m=0, safety_score=80)
    ranked, _ = rank_routes([b, a], ScoringWeights(0, 1, 1))
    assert ranked[0].metrics is a


def test_factor_missing_for_any_route_is_excluded_for_all_routes() -> None:
    routes = [make_metrics(20, safety_score=None), make_metrics(22, safety_score=95)]
    ranked, excluded = rank_routes(routes, ScoringWeights(0.4, 0.3, 0.3))

    assert excluded == {Factor.SAFETY}
    assert all(route.scores.safety is None for route in ranked)
    assert all(route.scores.elevation is not None for route in ranked)


def test_rank_routes_with_no_routes() -> None:
    assert rank_routes([], ScoringWeights(1, 1, 1)) == ([], set())


def test_explanations_describe_trade_offs() -> None:
    routes = [
        make_metrics(20, elevation_gain_m=200, safety_score=40, way_type_shares={"road": 1.0}),
        make_metrics(
            23,
            elevation_gain_m=60,
            safety_score=95,
            way_type_shares={"cycleway": 0.9, "street": 0.1},
        ),
    ]
    ranked, _ = rank_routes(routes, ScoringWeights(0.2, 0.4, 0.4))
    top, second = ranked

    assert top.metrics.distance_km == 23
    assert top.summary.startswith("Best overall balance of distance, elevation, and")
    assert "3.0 km longer than the shortest option" in top.highlights
    assert "Least climbing" in top.highlights
    assert "90% on cycleways or paths" in top.highlights

    assert "below route #1" in second.summary
    assert "Shortest option" in second.highlights
    assert "100% on busier roads" in second.highlights


def test_single_route_explanation() -> None:
    ranked, _ = rank_routes([make_metrics(15)], ScoringWeights(1, 1, 1))
    assert ranked[0].summary == "The only cycling route found for this trip."
    assert ranked[0].scores.distance == 100


# --- Target distance --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("distance_km", "expected"),
    [(30.0, 100.0), (33.0, 66.7), (27.0, 66.7), (39.0, 0.0), (15.0, 0.0)],
)
def test_target_distance_score_is_symmetric(distance_km: float, expected: float) -> None:
    assert target_distance_score(distance_km, target_km=30) == pytest.approx(expected, abs=0.1)


def test_target_ranking_prefers_route_closest_to_target_not_shortest() -> None:
    short = make_metrics(22)
    on_target = make_metrics(30.5)
    long = make_metrics(40)
    ranked, _ = rank_routes([short, long, on_target], ScoringWeights(1, 0, 0), target_km=30)

    assert [route.metrics for route in ranked] == [on_target, short, long]
    assert "On target: 30.5 km" in ranked[0].highlights
    assert "8.0 km under your 30 km target" in ranked[1].highlights
    assert ranked[0].summary.startswith("Best overall balance of target distance")


def test_backtracking_is_highlighted() -> None:
    ranked, _ = rank_routes([make_metrics(30, repeated_share=0.25)], ScoringWeights(1, 1, 1), 30)
    assert "25% of the ride doubles back on itself" in ranked[0].highlights


# --- Safety proxy -----------------------------------------------------------------------------


def test_safety_score_is_distance_weighted_by_way_type() -> None:
    assert estimate_safety_score({"cycleway": 0.5, "state_road": 0.5}) == pytest.approx(57.5)


def test_safety_score_is_unavailable_without_enough_data() -> None:
    assert estimate_safety_score({}) is None
    assert estimate_safety_score({"unknown": 0.6, "cycleway": 0.4}) is None
