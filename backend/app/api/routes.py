import uuid

from fastapi import APIRouter, status

from app.api.dependencies import PlannerDep, SessionDep, SettingsDep
from app.api.errors import ERROR_RESPONSES
from app.api.limits import RouteGenerationLimit
from app.core.errors import RouteNotFoundError
from app.db import repository
from app.domain import TripRequest
from app.schemas.route import (
    RouteDetailResponse,
    RouteRequest,
    RouteResponse,
    RouteSearchResponse,
    SearchContext,
)
from app.services.scoring import ScoringWeights

router = APIRouter(prefix="/api/routes", tags=["routes"])


@router.post(
    "",
    response_model=RouteSearchResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    dependencies=[RouteGenerationLimit],
)
async def create_routes(
    request: RouteRequest, planner: PlannerDep, session: SessionDep, settings: SettingsDep
) -> RouteSearchResponse:
    """Generate cycling routes for a loop, a target-distance ride, or an A-to-B trip, ranked."""
    preferences = request.preferences
    weights = ScoringWeights(
        distance=preferences.distance_weight if preferences else settings.default_distance_weight,
        elevation=(
            preferences.elevation_weight if preferences else settings.default_elevation_weight
        ),
        safety=preferences.safety_weight if preferences else settings.default_safety_weight,
    ).normalized()

    start = await planner.resolve_location(request.start.label, request.start.coordinate)
    destination = (
        await planner.resolve_location(request.destination.label, request.destination.coordinate)
        if request.destination
        else None
    )
    trip = TripRequest(
        mode=request.mode,
        start=start,
        destination=destination,
        target_distance_km=request.target_distance_km,
        bike_type=request.bike_type,
    )

    plan = await planner.plan(trip, weights)
    search = await repository.save_route_plan(session, plan, weights)
    return RouteSearchResponse.from_record(search)


@router.get("/{route_id}", response_model=RouteDetailResponse, responses=ERROR_RESPONSES)
async def get_route(route_id: uuid.UUID, session: SessionDep) -> RouteDetailResponse:
    """Fetch a previously generated route together with the search that produced it."""
    record = await repository.get_route(session, route_id)
    if record is None:
        raise RouteNotFoundError("Route not found.")
    return RouteDetailResponse(
        route=RouteResponse.from_record(record),
        search=SearchContext.from_record(record.search),
    )
