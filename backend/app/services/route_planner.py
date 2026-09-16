"""Orchestrates the route recommendation pipeline.

resolve locations -> generate candidate routes for the trip mode -> measure -> filter -> rank
"""

import asyncio
import logging

from app.core.errors import NoRouteFoundError, TripValidationError
from app.domain import (
    CandidateRoute,
    Coordinate,
    Factor,
    Location,
    RouteMetrics,
    RoutePlan,
    TripMode,
    TripRequest,
)
from app.services.geocoding import Geocoder
from app.services.geometry import haversine_m, path_length_m
from app.services.route_processing import build_route_metrics, route_cells, route_overlap
from app.services.routing import Router
from app.services.scoring import ScoringWeights, rank_routes
from app.services.trip_shapes import candidate_bearings, solve_waypoints

logger = logging.getLogger(__name__)

MIN_TRIP_LENGTH_M = 50.0
# Routed distance is typically 20-40% longer than straight-line distance between waypoints.
INITIAL_ROAD_FACTOR = 1.3
# Stop refining a candidate once it is this close to the target distance.
TARGET_TOLERANCE = 0.08
MAX_ATTEMPTS_PER_DIRECTION = 2
# A target-distance ride must be meaningfully longer than riding straight to the finish.
MIN_TARGET_TO_DIRECT_RATIO = 1.3
# Candidates sharing more than this much ground with a better candidate are dropped.
MAX_ROUTE_OVERLAP = 0.8
# Rides that double back on themselves more than this are dropped when better options exist.
MAX_REPEATED_SHARE = 0.4

EXCLUDED_FACTOR_WARNINGS = {
    Factor.ELEVATION: "Elevation data was unavailable, so routes were ranked without elevation.",
    Factor.SAFETY: (
        "Way-type data was incomplete for at least one route, so routes were ranked without "
        "the estimated safety score."
    ),
}


class RoutePlanner:
    def __init__(
        self,
        geocoder: Geocoder,
        router: Router,
        *,
        elevation_noise_threshold_m: float,
        default_speed_kmh: float,
        target_candidate_count: int,
        max_concurrent_routing_requests: int,
    ) -> None:
        self._geocoder = geocoder
        self._router = router
        self._noise_threshold_m = elevation_noise_threshold_m
        self._default_speed_kmh = default_speed_kmh
        self._target_candidate_count = target_candidate_count
        self._routing_slots = asyncio.Semaphore(max_concurrent_routing_requests)

    async def resolve_location(self, query: str, coordinate: Coordinate | None) -> Location:
        """Use coordinates picked from autocomplete as-is; geocode free text otherwise."""
        if coordinate is not None:
            return Location(query=query, display_name=query, coordinate=coordinate)
        return await self._geocoder.geocode(query)

    async def plan(self, trip: TripRequest, weights: ScoringWeights) -> RoutePlan:
        self._validate(trip)

        if trip.mode is TripMode.POINT_TO_POINT:
            assert trip.destination is not None
            candidates = await self._route(
                [trip.start.coordinate, trip.destination.coordinate], trip, alternatives=3
            )
        else:
            candidates = await self._target_distance_candidates(trip)

        logger.info(
            "%s trip from %r: %d candidate(s)", trip.mode, trip.start.query, len(candidates)
        )
        metrics = [
            build_route_metrics(
                candidate,
                noise_threshold_m=self._noise_threshold_m,
                default_speed_kmh=self._default_speed_kmh,
            )
            for candidate in candidates
        ]
        metrics = select_distinct_routes(metrics, trip.target_distance_km)

        ranked, excluded = rank_routes(metrics, weights, trip.target_distance_km)
        warnings = [EXCLUDED_FACTOR_WARNINGS[factor] for factor in Factor if factor in excluded]
        return RoutePlan(trip=trip, routes=ranked, warnings=warnings)

    @staticmethod
    def _validate(trip: TripRequest) -> None:
        if trip.mode is TripMode.LOOP:
            return
        if trip.destination is None:
            raise TripValidationError("Choose a destination for this trip.")
        direct_m = haversine_m(trip.start.coordinate, trip.destination.coordinate)
        if direct_m < MIN_TRIP_LENGTH_M:
            if trip.mode is TripMode.POINT_TO_POINT:
                raise TripValidationError("The start and destination are the same place.")
            raise TripValidationError(
                "The start and finish are the same place. Choose a loop instead."
            )
        if (
            trip.mode is TripMode.DISTANCE_GOAL
            and trip.target_distance_km
            and trip.target_distance_km * 1000 < direct_m * MIN_TARGET_TO_DIRECT_RATIO
        ):
            raise TripValidationError(
                f"The finish is {direct_m / 1000:.1f} km away in a straight line, so the target "
                "distance needs to be longer. Increase the distance or use point to point."
            )

    async def _route(
        self, waypoints: list[Coordinate], trip: TripRequest, alternatives: int = 1
    ) -> list[CandidateRoute]:
        async with self._routing_slots:
            return await self._router.get_routes(waypoints, trip.bike_type, alternatives)

    async def _target_distance_candidates(self, trip: TripRequest) -> list[CandidateRoute]:
        finish = trip.destination.coordinate if trip.destination else trip.start.coordinate
        bearings = candidate_bearings(trip.start.coordinate, finish, self._target_candidate_count)
        results = await asyncio.gather(
            *(self._route_towards_target(trip, finish, bearing) for bearing in bearings)
        )
        candidates = [candidate for candidate in results if candidate is not None]
        if not candidates:
            raise NoRouteFoundError(
                "Couldn't build a ride of that distance from here. "
                "Try a different distance or starting point."
            )
        return candidates

    async def _route_towards_target(
        self, trip: TripRequest, finish: Coordinate, bearing: float
    ) -> CandidateRoute | None:
        """Route through waypoints heading in `bearing`, adjusting the shape towards the target.

        The first attempt guesses how much longer roads are than straight lines; later attempts
        use the ratio actually observed for this direction.
        """
        assert trip.target_distance_km is not None
        target_m = trip.target_distance_km * 1000
        road_factor = INITIAL_ROAD_FACTOR
        best: CandidateRoute | None = None
        best_error = float("inf")

        for _ in range(MAX_ATTEMPTS_PER_DIRECTION):
            waypoints = solve_waypoints(
                trip.start.coordinate, finish, bearing, target_m / road_factor
            )
            if waypoints is None:
                break
            try:
                route = (await self._route(waypoints, trip))[0]
            except NoRouteFoundError:
                logger.info("No route heading %.0f degrees", bearing)
                break

            actual_m = route.distance_m or path_length_m(route.geometry)
            error = abs(actual_m / target_m - 1)
            if error < best_error:
                best, best_error = route, error
            if error <= TARGET_TOLERANCE:
                break
            road_factor = actual_m / path_length_m(waypoints)

        return best


def select_distinct_routes(
    routes: list[RouteMetrics], target_km: float | None
) -> list[RouteMetrics]:
    """Drop near-duplicate routes and, when alternatives exist, rides that mostly double back.

    Routes are considered best-first by closeness to the target (or shortest first without one),
    so the better of two near-identical routes is the one kept.
    """
    if target_km:
        ordered = sorted(routes, key=lambda route: abs(route.distance_km - target_km))
    else:
        ordered = sorted(routes, key=lambda route: route.distance_km)

    clean = [route for route in ordered if route.repeated_share <= MAX_REPEATED_SHARE]
    if clean:
        ordered = clean

    kept: list[RouteMetrics] = []
    kept_cells: list[set[tuple[int, int]]] = []
    for route in ordered:
        cells = route_cells(route.geometry)
        if all(route_overlap(cells, other) <= MAX_ROUTE_OVERLAP for other in kept_cells):
            kept.append(route)
            kept_cells.append(cells)
    return kept
