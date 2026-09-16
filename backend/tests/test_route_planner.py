"""Planner behaviour with an in-memory router that 'routes' along straight lines."""

import pytest

from app.core.errors import NoRouteFoundError, TripValidationError
from app.domain import BikeType, CandidateRoute, Coordinate, Location, TripMode, TripRequest
from app.services.geometry import path_length_m
from app.services.route_planner import RoutePlanner, select_distinct_routes
from app.services.scoring import ScoringWeights
from tests.factories import make_metrics

HOME = Location("Home", "Home, Waterloo, ON", Coordinate(43.4643, -80.5204))
NEARBY = Location("Park", "Park, Waterloo, ON", Coordinate(43.4800, -80.5000))
WEIGHTS = ScoringWeights(0.5, 0.2, 0.3)


class FakeRouter:
    """Connects waypoints with straight lines, stretched by a fixed 'road factor'."""

    def __init__(self, road_factor: float = 1.5, fail_after: int | None = None) -> None:
        self.road_factor = road_factor
        self.calls: list[tuple[list[Coordinate], BikeType, int]] = []
        self.fail_after = fail_after

    async def get_routes(
        self, waypoints: list[Coordinate], bike_type: BikeType, alternatives: int = 1
    ) -> list[CandidateRoute]:
        self.calls.append((waypoints, bike_type, alternatives))
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise NoRouteFoundError("no route")
        return [
            CandidateRoute(
                geometry=waypoints,
                distance_m=path_length_m(waypoints) * self.road_factor,
                duration_s=None,
                way_type_distances_m={"cycleway": 1.0},
                elevations=[300.0] * len(waypoints),
            )
        ]


class FakeGeocoder:
    async def geocode(self, query: str) -> Location:
        return Location(query, f"{query}, ON", Coordinate(43.0, -80.0))

    async def autocomplete(
        self, text: str, focus: Coordinate | None = None, limit: int = 5
    ) -> list[Location]:
        return []


def make_planner(router: FakeRouter) -> RoutePlanner:
    return RoutePlanner(
        FakeGeocoder(),
        router,
        elevation_noise_threshold_m=3,
        default_speed_kmh=18,
        target_candidate_count=4,
        max_concurrent_routing_requests=2,
    )


def trip(
    mode: TripMode, target_km: float | None = 30, destination: Location | None = None
) -> TripRequest:
    return TripRequest(mode, HOME, destination, target_km, BikeType.ROAD)


async def test_loop_routes_start_and_end_at_home_near_target_distance() -> None:
    router = FakeRouter(road_factor=1.5)
    plan = await make_planner(router).plan(trip(TripMode.LOOP), WEIGHTS)

    assert 1 <= len(plan.routes) <= 4
    for route in plan.routes:
        assert route.metrics.geometry[0] == HOME.coordinate
        assert route.metrics.geometry[-1] == HOME.coordinate
        assert route.metrics.distance_km == pytest.approx(30, rel=0.08)
    assert all(bike_type is BikeType.ROAD for _, bike_type, _ in router.calls)


async def test_loop_refines_waypoints_when_roads_are_longer_than_expected() -> None:
    router = FakeRouter(road_factor=1.8)  # much windier than the initial 1.3 guess
    plan = await make_planner(router).plan(trip(TripMode.LOOP), WEIGHTS)

    assert len(router.calls) == 8  # 4 directions x 2 attempts
    assert plan.routes[0].metrics.distance_km == pytest.approx(30, rel=0.02)


async def test_distance_goal_finishes_at_destination() -> None:
    plan = await make_planner(FakeRouter()).plan(
        trip(TripMode.DISTANCE_GOAL, destination=NEARBY), WEIGHTS
    )
    for route in plan.routes:
        assert route.metrics.geometry[-1] == NEARBY.coordinate
        assert route.metrics.distance_km == pytest.approx(30, rel=0.08)


async def test_point_to_point_asks_for_alternatives() -> None:
    router = FakeRouter()
    await make_planner(router).plan(
        trip(TripMode.POINT_TO_POINT, target_km=None, destination=NEARBY), WEIGHTS
    )
    [(waypoints, _, alternatives)] = router.calls
    assert waypoints == [HOME.coordinate, NEARBY.coordinate]
    assert alternatives == 3


async def test_distance_goal_shorter_than_direct_distance_is_rejected() -> None:
    far = Location("Far", "Far", Coordinate(43.9, -80.5))  # ~48 km away
    with pytest.raises(TripValidationError, match="straight line"):
        await make_planner(FakeRouter()).plan(
            trip(TripMode.DISTANCE_GOAL, target_km=30, destination=far), WEIGHTS
        )


async def test_same_start_and_finish_requires_loop() -> None:
    with pytest.raises(TripValidationError, match="loop"):
        await make_planner(FakeRouter()).plan(
            trip(TripMode.DISTANCE_GOAL, destination=HOME), WEIGHTS
        )


async def test_no_routable_direction_raises_no_route() -> None:
    with pytest.raises(NoRouteFoundError):
        await make_planner(FakeRouter(fail_after=0)).plan(trip(TripMode.LOOP), WEIGHTS)


async def test_resolve_location_uses_given_coordinates_without_geocoding() -> None:
    planner = make_planner(FakeRouter())
    picked = await planner.resolve_location("My house", Coordinate(43.1, -80.2))
    assert picked.coordinate == Coordinate(43.1, -80.2)
    typed = await planner.resolve_location("Guelph", None)
    assert typed.display_name == "Guelph, ON"


def test_near_duplicate_routes_are_removed_keeping_closest_to_target() -> None:
    path = [Coordinate(43.46, -80.52), Coordinate(43.50, -80.52), Coordinate(43.50, -80.46)]
    other_path = [Coordinate(43.46, -80.52), Coordinate(43.42, -80.60)]
    close = make_metrics(30.2, geometry=path)
    duplicate = make_metrics(33.0, geometry=path)
    different = make_metrics(35.0, geometry=other_path)

    kept = select_distinct_routes([duplicate, different, close], target_km=30)

    assert kept == [close, different]


def test_out_and_back_routes_are_dropped_when_loops_exist() -> None:
    loop = make_metrics(30, repeated_share=0.05, geometry=[Coordinate(43.46, -80.52)] * 2)
    out_and_back = make_metrics(
        30, repeated_share=0.6, geometry=[Coordinate(43.40, -80.40), Coordinate(43.41, -80.41)]
    )
    assert select_distinct_routes([out_and_back, loop], 30) == [loop]
    # ...but kept if nothing better exists.
    assert select_distinct_routes([out_and_back], 30) == [out_and_back]
