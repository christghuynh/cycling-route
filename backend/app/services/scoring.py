"""Transparent route scoring and ranking.

Every component score is on a 0-100 scale (higher is better):

* distance  - with a target distance (loops and distance goals): 100 when the route matches the
              target, falling linearly to 0 at `MAX_TARGET_DEVIATION` above or below it.
              Without a target (point to point): the shortest candidate scores 100, falling to 0
              for a route `MAX_DETOUR_RATIO` longer than the shortest.
* elevation - absolute climb density: 0 m of climbing per km scores 100, falling linearly to 0
              at `MAX_CLIMB_M_PER_KM`. Absolute so that two nearly identical flat routes are
              not artificially spread to the ends of the scale.
* safety    - the estimated safety proxy from `app.services.safety`, already 0-100.

The overall score is the weighted average of the components, using the user's preference
weights normalised to sum to 1.
"""

from dataclasses import dataclass

from app.domain import ComponentScores, Factor, RouteMetrics, ScoredRoute
from app.services.explanations import explain_route

MAX_DETOUR_RATIO = 0.5
MAX_TARGET_DEVIATION = 0.3
MAX_CLIMB_M_PER_KM = 25.0


@dataclass(frozen=True)
class ScoringWeights:
    distance: float
    elevation: float
    safety: float

    def __post_init__(self) -> None:
        values = (self.distance, self.elevation, self.safety)
        if any(value < 0 for value in values):
            raise ValueError("Weights must be non-negative")
        if sum(values) <= 0:
            raise ValueError("At least one weight must be greater than zero")

    def as_dict(self) -> dict[Factor, float]:
        return {
            Factor.DISTANCE: self.distance,
            Factor.ELEVATION: self.elevation,
            Factor.SAFETY: self.safety,
        }

    def normalized(self) -> "ScoringWeights":
        total = self.distance + self.elevation + self.safety
        return ScoringWeights(self.distance / total, self.elevation / total, self.safety / total)


def _clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


def distance_score(distance_km: float, shortest_km: float) -> float:
    if shortest_km <= 0 or distance_km <= shortest_km:
        return 100.0
    detour_ratio = distance_km / shortest_km - 1
    return _clamp_score(100.0 * (1 - detour_ratio / MAX_DETOUR_RATIO))


def target_distance_score(distance_km: float, target_km: float) -> float:
    deviation = abs(distance_km / target_km - 1)
    return _clamp_score(100.0 * (1 - deviation / MAX_TARGET_DEVIATION))


def elevation_score(elevation_gain_m: float, distance_km: float) -> float:
    if distance_km <= 0:
        return 100.0
    climb_per_km = elevation_gain_m / distance_km
    return _clamp_score(100.0 * (1 - climb_per_km / MAX_CLIMB_M_PER_KM))


def weighted_overall_score(
    components: dict[Factor, float | None], weights: ScoringWeights
) -> float:
    """Weighted average of the available components.

    Missing components are left out and the remaining weights are re-normalised. If every
    available component has zero weight, they are averaged equally.
    """
    available = {factor: score for factor, score in components.items() if score is not None}
    if not available:
        raise ValueError("At least one component score is required")

    weight_by_factor = weights.as_dict()
    total_weight = sum(weight_by_factor[factor] for factor in available)
    if total_weight <= 0:
        return sum(available.values()) / len(available)
    return sum(weight_by_factor[factor] * score for factor, score in available.items()) / (
        total_weight
    )


def unavailable_factors(routes: list[RouteMetrics]) -> set[Factor]:
    """Factors that cannot be compared fairly because at least one route lacks the data."""
    missing: set[Factor] = set()
    if any(route.elevation_gain_m is None for route in routes):
        missing.add(Factor.ELEVATION)
    if any(route.safety_score is None for route in routes):
        missing.add(Factor.SAFETY)
    return missing


def score_route(
    route: RouteMetrics,
    shortest_km: float,
    target_km: float | None,
    weights: ScoringWeights,
    excluded: set[Factor],
) -> ComponentScores:
    if target_km:
        distance = target_distance_score(route.distance_km, target_km)
    else:
        distance = distance_score(route.distance_km, shortest_km)
    elevation = (
        elevation_score(route.elevation_gain_m, route.distance_km)
        if Factor.ELEVATION not in excluded and route.elevation_gain_m is not None
        else None
    )
    safety = route.safety_score if Factor.SAFETY not in excluded else None
    overall = weighted_overall_score(
        {Factor.DISTANCE: distance, Factor.ELEVATION: elevation, Factor.SAFETY: safety},
        weights,
    )
    return ComponentScores(distance=distance, elevation=elevation, safety=safety, overall=overall)


def rank_routes(
    routes: list[RouteMetrics], weights: ScoringWeights, target_km: float | None = None
) -> tuple[list[ScoredRoute], set[Factor]]:
    """Score and sort routes best-first. Also returns the factors excluded for missing data."""
    if not routes:
        return [], set()

    weights = weights.normalized()
    excluded = unavailable_factors(routes)
    shortest_km = min(route.distance_km for route in routes)

    def tie_breaker(route: RouteMetrics) -> float:
        return abs(route.distance_km - target_km) if target_km else route.distance_km

    scored = [
        (route, score_route(route, shortest_km, target_km, weights, excluded)) for route in routes
    ]
    scored.sort(key=lambda pair: (-pair[1].overall, tie_breaker(pair[0])))

    all_metrics = [route for route, _ in scored]
    all_scores = [scores for _, scores in scored]
    ranked = []
    for index, (route, scores) in enumerate(scored):
        summary, highlights = explain_route(
            index, all_metrics, all_scores, weights.as_dict(), target_km
        )
        ranked.append(
            ScoredRoute(
                rank=index + 1,
                metrics=route,
                scores=scores,
                summary=summary,
                highlights=highlights,
            )
        )
    return ranked, excluded
