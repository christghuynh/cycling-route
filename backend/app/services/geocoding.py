"""Geocoding: turn place names into coordinates, including type-ahead suggestions.

OpenRouteService hosts a Pelias geocoder, so the same key used for routing covers geocoding.
Two endpoints are used: `/geocode/autocomplete` is built for type-ahead and handles partial
input, but returns nothing when an exact house number is not in the data. `/geocode/search` is
more forgiving and falls back to the street, so it is tried when autocomplete finds nothing.

Both are ranked around a focus point (the visible map area) so that ambiguous names such as
"Waterloo" resolve to the one the rider is looking at.
"""

import logging
from typing import Protocol

import httpx
from pydantic import BaseModel

from app.core.errors import ConfigurationError, ExternalServiceError, LocationNotFoundError
from app.domain import Coordinate, Location
from app.services.http import parse_response, send_request

logger = logging.getLogger(__name__)

SERVICE_NAME = "geocoding"

AUTOCOMPLETE_PATH = "/geocode/autocomplete"
SEARCH_PATH = "/geocode/search"


class Geocoder(Protocol):
    async def geocode(self, query: str) -> Location: ...

    async def autocomplete(
        self, text: str, focus: Coordinate | None = None, limit: int = 5
    ) -> list[Location]: ...


class _PeliasGeometry(BaseModel):
    coordinates: tuple[float, float]  # [lon, lat]


class _PeliasProperties(BaseModel):
    label: str


class _PeliasFeature(BaseModel):
    geometry: _PeliasGeometry
    properties: _PeliasProperties


class _PeliasResults(BaseModel):
    features: list[_PeliasFeature] = []


class OpenRouteServiceGeocoder:
    """Geocoder backed by the OpenRouteService-hosted Pelias API (same key as routing)."""

    def __init__(self, client: httpx.AsyncClient, base_url: str, api_key: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def geocode(self, query: str) -> Location:
        results = await self._request(SEARCH_PATH, query, focus=None, limit=1)
        if not results:
            raise LocationNotFoundError(f"Could not find a location matching '{query}'.")
        return results[0]

    async def autocomplete(
        self, text: str, focus: Coordinate | None = None, limit: int = 5
    ) -> list[Location]:
        suggestions = await self._request(AUTOCOMPLETE_PATH, text, focus, limit)
        if suggestions:
            return suggestions
        # Autocomplete draws a blank on addresses whose house number is not mapped; the search
        # endpoint still finds the street.
        logger.info("Autocomplete found nothing for %r; falling back to search", text)
        return await self._request(SEARCH_PATH, text, focus, limit)

    async def _request(
        self, path: str, text: str, focus: Coordinate | None, limit: int
    ) -> list[Location]:
        if not self._api_key:
            raise ConfigurationError(
                "The geocoding service is not configured. Set ORS_API_KEY on the backend."
            )
        params: dict[str, str | int | float] = {"text": text, "size": limit}
        if focus is not None:
            params["focus.point.lat"] = focus.lat
            params["focus.point.lon"] = focus.lon

        response = await send_request(
            self._client,
            SERVICE_NAME,
            "GET",
            f"{self._base_url}{path}",
            params=params,
            headers={"Authorization": self._api_key},
        )
        if response.status_code in (401, 403):
            raise ExternalServiceError(SERVICE_NAME, "The geocoding service rejected the API key.")
        if response.status_code != 200:
            logger.error("Geocoder returned %s: %s", response.status_code, response.text[:500])
            raise ExternalServiceError(SERVICE_NAME, "The geocoding service rejected the request.")

        features = parse_response(response, _PeliasResults, SERVICE_NAME).features
        return [
            Location(
                query=text,
                display_name=feature.properties.label,
                coordinate=Coordinate(
                    lat=feature.geometry.coordinates[1], lon=feature.geometry.coordinates[0]
                ),
            )
            for feature in features
        ][:limit]
