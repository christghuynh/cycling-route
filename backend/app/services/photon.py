"""Photon geocoder: type-ahead suggestions without spending API quota.

Photon (by Komoot) searches OpenStreetMap data, is built for partial and messy type-ahead input,
and needs no API key. Suggestions fire as the rider types, which on a free OpenRouteService key
exhausts its roughly 100 daily geocoding calls within an evening of use, so suggestions come from
Photon first. Its public server asks for fair use rather than enforcing a quota, and it can be
self-hosted by changing `PHOTON_BASE_URL`.
"""

import logging

import httpx
from pydantic import BaseModel

from app.core.errors import ExternalServiceError, LocationNotFoundError
from app.domain import Coordinate, Location
from app.services.http import parse_response, send_request

logger = logging.getLogger(__name__)

SERVICE_NAME = "geocoding"


class _PhotonGeometry(BaseModel):
    coordinates: tuple[float, float]  # [lon, lat]


class _PhotonProperties(BaseModel):
    name: str | None = None
    housenumber: str | None = None
    street: str | None = None
    city: str | None = None
    district: str | None = None
    county: str | None = None
    state: str | None = None
    country: str | None = None


class _PhotonFeature(BaseModel):
    geometry: _PhotonGeometry
    properties: _PhotonProperties


class _PhotonResults(BaseModel):
    features: list[_PhotonFeature] = []


def _street_address(properties: _PhotonProperties) -> str | None:
    if not properties.street:
        return None
    if properties.housenumber:
        return f"{properties.housenumber} {properties.street}"
    return properties.street


def build_label(properties: _PhotonProperties, include_name: bool = True) -> str:
    """Readable one-line label, e.g. "TSUJIRI, 330 Phillip Street, Waterloo, Ontario, Canada"."""
    address = _street_address(properties)
    name = properties.name if include_name else None
    parts = [
        name or address,
        address,
        properties.city or properties.district or properties.county,
        properties.state,
        properties.country,
    ]
    seen: list[str] = []
    for part in parts:
        if part and part not in seen:
            seen.append(part)
    return ", ".join(seen)


def _address_key(properties: _PhotonProperties) -> tuple[str, str, str] | None:
    """Identifies results sharing one street address, so they can be collapsed into one."""
    if not (properties.housenumber and properties.street):
        return None
    return (
        properties.housenumber,
        properties.street.casefold(),
        (properties.city or properties.state or "").casefold(),
    )


def to_locations(features: list[_PhotonFeature], query: str) -> list[Location]:
    """Convert Photon features into locations, collapsing duplicates.

    Several businesses often share one street address. When that happens the address itself is
    what the rider means, so those results become a single entry labelled with the address.
    """
    shared_addresses = {
        key
        for key in (_address_key(feature.properties) for feature in features)
        if key is not None and sum(1 for f in features if _address_key(f.properties) == key) > 1
    }

    locations: list[Location] = []
    seen_labels: set[str] = set()
    for feature in features:
        properties = feature.properties
        at_shared_address = _address_key(properties) in shared_addresses
        label = build_label(properties, include_name=not at_shared_address)
        if not label or label.casefold() in seen_labels:
            continue
        seen_labels.add(label.casefold())
        locations.append(
            Location(
                query=query,
                display_name=label,
                coordinate=Coordinate(
                    lat=feature.geometry.coordinates[1], lon=feature.geometry.coordinates[0]
                ),
            )
        )
    return locations


class PhotonGeocoder:
    """Geocoder backed by the Photon API (OpenStreetMap data, no API key)."""

    def __init__(self, client: httpx.AsyncClient, base_url: str, user_agent: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent

    async def geocode(self, query: str) -> Location:
        results = await self._search(query, focus=None, limit=1)
        if not results:
            raise LocationNotFoundError(f"Could not find a location matching '{query}'.")
        return results[0]

    async def autocomplete(
        self, text: str, focus: Coordinate | None = None, limit: int = 5
    ) -> list[Location]:
        return await self._search(text, focus, limit)

    async def _search(self, text: str, focus: Coordinate | None, limit: int) -> list[Location]:
        params: dict[str, str | int | float] = {
            "q": text,
            # Ask for extra results because duplicates at one address get collapsed.
            "limit": limit * 3,
            "lang": "en",
        }
        if focus is not None:
            params["lat"] = focus.lat
            params["lon"] = focus.lon

        response = await send_request(
            self._client,
            SERVICE_NAME,
            "GET",
            f"{self._base_url}/api",
            params=params,
            headers={"User-Agent": self._user_agent},
        )
        if response.status_code != 200:
            logger.error("Photon returned %s: %s", response.status_code, response.text[:500])
            raise ExternalServiceError(SERVICE_NAME, "The geocoding service rejected the request.")

        features = parse_response(response, _PhotonResults, SERVICE_NAME).features
        return to_locations(features, text)[:limit]
