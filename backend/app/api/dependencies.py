from typing import Annotated

import httpx
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.database import get_session
from app.services.geocoding import FallbackGeocoder, OpenRouteServiceGeocoder
from app.services.photon import PhotonGeocoder
from app.services.route_planner import RoutePlanner
from app.services.routing import OpenRouteServiceRouter


def get_settings_from_app(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_geocoder(request: Request) -> FallbackGeocoder:
    """Photon for suggestions (no quota), OpenRouteService when Photon cannot answer."""
    settings = get_settings_from_app(request)
    client: httpx.AsyncClient = request.app.state.http_client
    return FallbackGeocoder(
        primary=PhotonGeocoder(client, settings.photon_base_url, settings.geocoder_user_agent),
        fallback=OpenRouteServiceGeocoder(client, settings.ors_base_url, settings.ors_api_key),
    )


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


def client_identifier(request: Request) -> str:
    """Identify the caller for rate limiting.

    Behind Vercel (or any proxy) the socket address is the proxy, so the first entry of
    X-Forwarded-For is used when present.
    """
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()[:100]
    return request.client.host if request.client else "unknown"


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_from_app)]
PlannerDep = Annotated[RoutePlanner, Depends(get_route_planner)]
GeocoderDep = Annotated[FallbackGeocoder, Depends(get_geocoder)]
