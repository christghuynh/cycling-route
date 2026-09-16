"""Human-readable reasons for why a route received its rank."""

from app.domain import ComponentScores, Factor, RouteMetrics
from app.services.safety import MAJOR_ROAD_WAY_TYPES, SEPARATED_WAY_TYPES, share_of

FACTOR_LABELS = {
    Factor.DISTANCE: "distance",
    Factor.ELEVATION: "elevation",
    Factor.SAFETY: "estimated safety",
}
TARGET_DISTANCE_LABEL = "how close it is to your target distance"

# Differences smaller than these are treated as ties in highlights.
DISTANCE_TOLERANCE_KM = 0.1
ON_TARGET_TOLERANCE = 0.03
ELEVATION_TOLERANCE_M = 5.0
MAJOR_ROAD_HIGHLIGHT_SHARE = 0.2
REPEATED_HIGHLIGHT_SHARE = 0.1


def _component(scores: ComponentScores, factor: Factor) -> float | None:
    return {
        Factor.DISTANCE: scores.distance,
        Factor.ELEVATION: scores.elevation,
        Factor.SAFETY: scores.safety,
    }[factor]


def _used_factors(scores: ComponentScores) -> list[Factor]:
    return [factor for factor in Factor if _component(scores, factor) is not None]


def _label(factor: Factor, target_km: float | None) -> str:
    if factor is Factor.DISTANCE and target_km:
        return "target distance"
    return FACTOR_LABELS[factor]


def _join_labels(labels: list[str]) -> str:
    if len(labels) <= 2:
        return " and ".join(labels)
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _summary(
    index: int,
    all_scores: list[ComponentScores],
    weights: dict[Factor, float],
    target_km: float | None,
) -> str:
    scores = all_scores[index]
    if len(all_scores) == 1:
        return "The only cycling route found for this trip."
    if index == 0:
        labels = [_label(factor, target_km) for factor in _used_factors(scores)]
        return f"Best overall balance of {_join_labels(labels)} for your preferences."

    best = all_scores[0]
    gap = best.overall - scores.overall
    # The factor that cost this route the most weighted points relative to the top route.
    losses = {
        factor: weights[factor]
        * ((_component(best, factor) or 0) - (_component(scores, factor) or 0))
        for factor in _used_factors(scores)
    }
    main_factor, main_loss = max(losses.items(), key=lambda item: item[1])
    points = round(gap)
    if points < 1 or main_loss <= 0:
        return "Scores almost the same as the top route."
    unit = "point" if points == 1 else "points"
    reason = (
        TARGET_DISTANCE_LABEL
        if main_factor is Factor.DISTANCE and target_km
        else FACTOR_LABELS[main_factor]
    )
    return f"Scores {points} {unit} below route #1, mainly because of {reason}."


def _distance_highlight(
    route: RouteMetrics, all_metrics: list[RouteMetrics], target_km: float | None
) -> str | None:
    if target_km:
        difference = route.distance_km - target_km
        if abs(difference) <= target_km * ON_TARGET_TOLERANCE:
            return f"On target: {route.distance_km:.1f} km"
        direction = "over" if difference > 0 else "under"
        return f"{abs(difference):.1f} km {direction} your {target_km:g} km target"

    if len(all_metrics) == 1:
        return None
    extra_km = route.distance_km - min(r.distance_km for r in all_metrics)
    if extra_km <= DISTANCE_TOLERANCE_KM:
        return "Shortest option"
    return f"{extra_km:.1f} km longer than the shortest option"


def _highlights(index: int, all_metrics: list[RouteMetrics], target_km: float | None) -> list[str]:
    route = all_metrics[index]
    compare = len(all_metrics) > 1
    highlights: list[str] = []

    if distance_highlight := _distance_highlight(route, all_metrics, target_km):
        highlights.append(distance_highlight)

    if route.elevation_gain_m is not None:
        gains = [r.elevation_gain_m for r in all_metrics if r.elevation_gain_m is not None]
        extra_m = route.elevation_gain_m - min(gains)
        if not compare:
            highlights.append(f"{route.elevation_gain_m:.0f} m of climbing")
        elif extra_m <= ELEVATION_TOLERANCE_M:
            highlights.append("Least climbing")
        else:
            highlights.append(f"{extra_m:.0f} m more climbing than the flattest option")

    if route.way_type_shares:
        separated = share_of(route.way_type_shares, SEPARATED_WAY_TYPES)
        major = share_of(route.way_type_shares, MAJOR_ROAD_WAY_TYPES)
        if separated > 0:
            highlights.append(f"{separated:.0%} on cycleways or paths")
        if major >= MAJOR_ROAD_HIGHLIGHT_SHARE:
            highlights.append(f"{major:.0%} on busier roads")

    if route.repeated_share >= REPEATED_HIGHLIGHT_SHARE:
        highlights.append(f"{route.repeated_share:.0%} of the ride doubles back on itself")

    return highlights


def explain_route(
    index: int,
    all_metrics: list[RouteMetrics],
    all_scores: list[ComponentScores],
    weights: dict[Factor, float],
    target_km: float | None = None,
) -> tuple[str, list[str]]:
    """Summary sentence and factual highlights for the route at `index` in a ranked list."""
    return (
        _summary(index, all_scores, weights, target_km),
        _highlights(index, all_metrics, target_km),
    )
