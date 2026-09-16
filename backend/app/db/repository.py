"""Persistence for route searches. Knows about the database, not about route generation."""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PersistenceError
from app.db.models import RouteRecord, RouteSearch
from app.domain import RoutePlan, ScoredRoute
from app.services.scoring import ScoringWeights

logger = logging.getLogger(__name__)


def _route_record(route: ScoredRoute) -> RouteRecord:
    metrics, scores = route.metrics, route.scores
    return RouteRecord(
        rank=route.rank,
        geometry=[[point.lat, point.lon] for point in metrics.geometry],
        elevation_profile=[[p.distance_km, p.elevation_m] for p in metrics.elevation_profile],
        way_type_shares=metrics.way_type_shares,
        distance_km=metrics.distance_km,
        elevation_gain_m=metrics.elevation_gain_m,
        duration_min=metrics.duration_min,
        safety_score=scores.safety,
        distance_score=scores.distance,
        elevation_score=scores.elevation,
        overall_score=scores.overall,
        repeated_share=metrics.repeated_share,
        summary=route.summary,
        highlights=route.highlights,
    )


async def save_route_plan(
    session: AsyncSession, plan: RoutePlan, weights: ScoringWeights
) -> RouteSearch:
    trip = plan.trip
    destination = trip.destination
    search = RouteSearch(
        mode=trip.mode.value,
        bike_type=trip.bike_type.value,
        target_distance_km=trip.target_distance_km,
        start_query=trip.start.query,
        start_name=trip.start.display_name,
        start_lat=trip.start.coordinate.lat,
        start_lon=trip.start.coordinate.lon,
        destination_query=destination.query if destination else None,
        destination_name=destination.display_name if destination else None,
        destination_lat=destination.coordinate.lat if destination else None,
        destination_lon=destination.coordinate.lon if destination else None,
        distance_weight=weights.distance,
        elevation_weight=weights.elevation,
        safety_weight=weights.safety,
        warnings=plan.warnings,
        routes=[_route_record(route) for route in plan.routes],
    )
    try:
        session.add(search)
        await session.commit()
        await session.refresh(search, attribute_names=["routes"])
    except SQLAlchemyError as exc:
        await session.rollback()
        logger.exception("Failed to save route search")
        raise PersistenceError("The generated routes could not be saved.") from exc
    return search


async def get_route(session: AsyncSession, route_id: uuid.UUID) -> RouteRecord | None:
    try:
        result = await session.execute(select(RouteRecord).where(RouteRecord.id == route_id))
    except SQLAlchemyError as exc:
        logger.exception("Failed to load route %s", route_id)
        raise PersistenceError("The route could not be loaded.") from exc
    return result.scalar_one_or_none()
