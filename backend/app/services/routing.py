"""Routing: request cycling routes through a list of waypoints."""

import logging
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from app.core.errors import ConfigurationError, ExternalServiceError, NoRouteFoundError
from app.domain import BikeType, CandidateRoute, Coordinate
from app.services.geometry import decode_polyline, haversine_m
from app.services.http import parse_response, send_request

logger = logging.getLogger(__name__)

SERVICE_NAME = "routing"

# OpenRouteService "waytype" extra-info codes, mapped to provider-neutral names.
# https://giscience.github.io/openrouteservice/api-reference/endpoints/directions/extra-info/
ORS_WAY_TYPES = {
    0: "unknown",
    1: "state_road",
    2: "road",
    3: "street",
    4: "path",
    5: "track",
    6: "cycleway",
    7: "footway",
    8: "steps",
    9: "ferry",
    10: "construction",
}

ORS_PROFILES = {
    BikeType.ROAD: "cycling-road",
    BikeType.HYBRID: "cycling-regular",
    BikeType.MOUNTAIN: "cycling-mountain",
}

# ORS error codes meaning "no route possible" rather than a service failure.
ORS_NO_ROUTE_CODES = {2004, 2009, 2010}

# ORS only computes alternative routes for trips up to 100 km.
ALTERNATIVES_MAX_STRAIGHT_LINE_KM = 80.0
# Via points are generated geometrically and may land in a field or lake; let ORS snap them to
# the nearest road however far away it is (-1). Start and finish use a bounded search radius.
ENDPOINT_SNAP_RADIUS_M = 1000
VIA_POINT_SNAP_RADIUS_M = -1


class Router(Protocol):
    async def get_routes(
        self,
        waypoints: list[Coordinate],
        bike_type: BikeType,
        alternatives: int = 1,
    ) -> list[CandidateRoute]: ...


class _OrsSummary(BaseModel):
    distance: float | None = None
    duration: float | None = None


class _OrsExtraSummary(BaseModel):
    value: float
    distance: float


class _OrsExtra(BaseModel):
    summary: list[_OrsExtraSummary] = []


class _OrsRoute(BaseModel):
    summary: _OrsSummary
    geometry: str
    extras: dict[str, _OrsExtra] = {}


class _OrsDirections(BaseModel):
    routes: list[_OrsRoute]


class OpenRouteServiceRouter:
    """Router backed by the OpenRouteService cycling directions profiles."""

    def __init__(self, client: httpx.AsyncClient, base_url: str, api_key: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def get_routes(
        self,
        waypoints: list[Coordinate],
        bike_type: BikeType,
        alternatives: int = 1,
    ) -> list[CandidateRoute]:
        """Routes through `waypoints` in order.

        `alternatives` > 1 asks for alternative routes, which ORS only supports for two
        waypoints on shorter trips; the request silently falls back to one route otherwise.
        """
        if not self._api_key:
            raise ConfigurationError(
                "The routing service is not configured. Set ORS_API_KEY on the backend."
            )
        if len(waypoints) < 2:
            raise ValueError("At least two waypoints are required")

        response = await send_request(
            self._client,
            SERVICE_NAME,
            "POST",
            f"{self._base_url}/v2/directions/{ORS_PROFILES[bike_type]}/json",
            json=self._build_body(waypoints, alternatives),
            headers={"Authorization": self._api_key},
        )
        if response.status_code != 200:
            self._raise_for_client_error(response)

        directions = parse_response(response, _OrsDirections, SERVICE_NAME)
        routes = [self._to_candidate(route) for route in directions.routes]
        routes = [route for route in routes if len(route.geometry) >= 2]
        if not routes:
            raise NoRouteFoundError("No cycling route could be found between these locations.")
        return routes

    @staticmethod
    def _build_body(waypoints: list[Coordinate], alternatives: int) -> dict[str, Any]:
        radiuses = [VIA_POINT_SNAP_RADIUS_M] * len(waypoints)
        radiuses[0] = radiuses[-1] = ENDPOINT_SNAP_RADIUS_M
        body: dict[str, Any] = {
            "coordinates": [[point.lon, point.lat] for point in waypoints],
            "radiuses": radiuses,
            "elevation": True,
            "instructions": False,
            "extra_info": ["waytype"],
            "options": {"avoid_features": ["steps", "ferries"]},
        }
        straight_line_km = haversine_m(waypoints[0], waypoints[-1]) / 1000
        if (
            alternatives > 1
            and len(waypoints) == 2
            and straight_line_km <= ALTERNATIVES_MAX_STRAIGHT_LINE_KM
        ):
            body["alternative_routes"] = {
                "target_count": min(alternatives, 3),
                "weight_factor": 1.6,
                "share_factor": 0.6,
            }
        return body

    @staticmethod
    def _raise_for_client_error(response: httpx.Response) -> None:
        code, message = _parse_ors_error(response)
        logger.warning("ORS returned %s (code=%s): %s", response.status_code, code, message)
        if response.status_code in (401, 403):
            raise ExternalServiceError(SERVICE_NAME, "The routing service rejected the API key.")
        if code in ORS_NO_ROUTE_CODES:
            raise NoRouteFoundError(
                "No cycling route could be found for these locations. "
                "They may be too far apart or not reachable by bike."
            )
        raise ExternalServiceError(SERVICE_NAME, "The routing service rejected the request.")

    @staticmethod
    def _to_candidate(route: _OrsRoute) -> CandidateRoute:
        try:
            decoded = decode_polyline(route.geometry, with_elevation=True)
        except ValueError as exc:
            raise ExternalServiceError(
                SERVICE_NAME, "The routing service returned an invalid route geometry."
            ) from exc

        way_types: dict[str, float] = {}
        # The live API returns "waytype"; some documentation shows "waytypes".
        if waytypes := (route.extras.get("waytype") or route.extras.get("waytypes")):
            for item in waytypes.summary:
                name = ORS_WAY_TYPES.get(int(item.value), "unknown")
                way_types[name] = way_types.get(name, 0.0) + item.distance

        return CandidateRoute(
            geometry=decoded.coordinates,
            distance_m=route.summary.distance,
            duration_s=route.summary.duration,
            way_type_distances_m=way_types,
            elevations=decoded.elevations,
        )


def _parse_ors_error(response: httpx.Response) -> tuple[int | None, str]:
    try:
        payload = response.json()
    except ValueError:
        return None, response.text[:500]
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        code = error.get("code")
        return (code if isinstance(code, int) else None), str(error.get("message", ""))
    return None, str(error or payload)
