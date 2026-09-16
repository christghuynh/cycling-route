from typing import Annotated

import httpx
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.database import get_session
from app.services.geocoding import OpenRouteServiceGeocoder
from app.services.route_planner import RoutePlanner
from app.services.routing import OpenRouteServiceRouter


def get_settings_from_app(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_geocoder(request: Request) -> OpenRouteServiceGeocoder:
    settings = get_settings_from_app(request)
    client: httpx.AsyncClient = request.app.state.http_client
    return OpenRouteServiceGeocoder(client, settings.ors_base_url, settings.ors_api_key)


def get_route_planner(request: Request) -> RoutePlanner:
    settings = get_settings_from_app(request)
    client: httpx.AsyncClient = request.app.state.http_client
    return RoutePlanner(
        geocoder=get_geocoder(request),
        router=OpenRouteServiceRouter(client, settings.ors_base_url, settings.ors_api_key),
        elevation_noise_threshold_m=settings.elevation_noise_threshold_m,
        default_speed_kmh=settings.default_cycling_speed_kmh,
        target_candidate_count=settings.target_candidate_count,
        max_concurrent_routing_requests=settings.max_concurrent_routing_requests,
    )


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_from_app)]
PlannerDep = Annotated[RoutePlanner, Depends(get_route_planner)]
GeocoderDep = Annotated[OpenRouteServiceGeocoder, Depends(get_geocoder)]
