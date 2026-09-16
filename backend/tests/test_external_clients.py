"""Tests for the OpenRouteService clients: request shape and response parsing."""

import json

import httpx
import pytest
import respx

from app.core.errors import (
    ConfigurationError,
    ExternalServiceError,
    LocationNotFoundError,
    NoRouteFoundError,
    RateLimitedError,
)
from app.domain import BikeType, Coordinate
from app.services.geocoding import OpenRouteServiceGeocoder
from app.services.routing import OpenRouteServiceRouter
from tests.factories import (
    DIRECT_ROUTE_POINTS,
    WATERLOO_LABEL,
    default_ors_response,
    ors_route,
    pelias_response,
)

ORS_BASE = "https://ors.test"
START = Coordinate(43.4643, -80.5204)
END = Coordinate(43.3616, -80.3144)


def directions_url(profile: str = "cycling-regular") -> str:
    return f"{ORS_BASE}/v2/directions/{profile}/json"


@pytest.fixture
async def client() -> httpx.AsyncClient:
    async with httpx.AsyncClient() as http_client:
        yield http_client


def make_router(client: httpx.AsyncClient, api_key: str = "secret") -> OpenRouteServiceRouter:
    return OpenRouteServiceRouter(client, ORS_BASE, api_key)


# --- OpenRouteService directions --------------------------------------------------------------


@respx.mock
async def test_ors_response_is_parsed_into_candidates(client: httpx.AsyncClient) -> None:
    route = respx.post(directions_url()).mock(
        return_value=httpx.Response(200, json=default_ors_response())
    )

    candidates = await make_router(client).get_routes([START, END], BikeType.HYBRID, 3)

    assert len(candidates) == 2
    first = candidates[0]
    assert first.distance_m == 21_000
    assert first.duration_s == 4_500
    assert [(c.lat, c.lon) for c in first.geometry] == DIRECT_ROUTE_POINTS
    assert first.elevations == [300.0, 301.0, 302.0]
    assert first.way_type_distances_m == {"road": 15_000, "street": 6_000}

    request = route.calls.last.request
    assert request.headers["Authorization"] == "secret"
    body = json.loads(request.content)
    assert body["coordinates"] == [[START.lon, START.lat], [END.lon, END.lat]]
    assert body["elevation"] is True
    assert body["alternative_routes"]["target_count"] == 3
    assert body["extra_info"] == ["waytype"]


@pytest.mark.parametrize(
    ("bike_type", "profile"),
    [
        (BikeType.ROAD, "cycling-road"),
        (BikeType.HYBRID, "cycling-regular"),
        (BikeType.MOUNTAIN, "cycling-mountain"),
    ],
)
@respx.mock
async def test_bike_type_selects_ors_profile(
    client: httpx.AsyncClient, bike_type: BikeType, profile: str
) -> None:
    route = respx.post(directions_url(profile)).mock(
        return_value=httpx.Response(200, json=default_ors_response())
    )
    await make_router(client).get_routes([START, END], bike_type)
    assert route.called


@respx.mock
async def test_via_points_snap_to_nearest_road_without_alternatives(
    client: httpx.AsyncClient,
) -> None:
    route = respx.post(directions_url()).mock(
        return_value=httpx.Response(200, json=default_ors_response())
    )
    via = [Coordinate(43.5, -80.5), Coordinate(43.5, -80.4)]
    await make_router(client).get_routes([START, *via, START], BikeType.HYBRID, alternatives=3)

    body = json.loads(route.calls.last.request.content)
    assert len(body["coordinates"]) == 4
    assert body["radiuses"] == [1000, -1, -1, 1000]
    assert "alternative_routes" not in body


@respx.mock
async def test_ors_skips_alternatives_for_long_trips(client: httpx.AsyncClient) -> None:
    route = respx.post(directions_url()).mock(
        return_value=httpx.Response(200, json=default_ors_response())
    )
    await make_router(client).get_routes([START, Coordinate(45.5, -73.6)], BikeType.HYBRID, 3)
    assert "alternative_routes" not in json.loads(route.calls.last.request.content)


@pytest.mark.parametrize("extras_key", ["waytype", "waytypes"])
@respx.mock
async def test_way_types_are_read_under_either_extras_key(
    client: httpx.AsyncClient, extras_key: str
) -> None:
    route = ors_route(DIRECT_ROUTE_POINTS, 21_000, 4_500, {6: 15_000, 1: 6_000})
    route["extras"] = {extras_key: route["extras"]["waytype"]}
    respx.post(directions_url()).mock(return_value=httpx.Response(200, json={"routes": [route]}))

    [candidate] = await make_router(client).get_routes([START, END], BikeType.HYBRID)

    assert candidate.way_type_distances_m == {"cycleway": 15_000, "state_road": 6_000}


@respx.mock
async def test_ors_route_without_extras_has_no_way_types(client: httpx.AsyncClient) -> None:
    payload = {"routes": [ors_route(DIRECT_ROUTE_POINTS, 21_000, 4_500)]}
    respx.post(directions_url()).mock(return_value=httpx.Response(200, json=payload))
    [candidate] = await make_router(client).get_routes([START, END], BikeType.HYBRID)
    assert candidate.way_type_distances_m == {}


@respx.mock
async def test_ors_empty_routes_raise_no_route(client: httpx.AsyncClient) -> None:
    respx.post(directions_url()).mock(return_value=httpx.Response(200, json={"routes": []}))
    with pytest.raises(NoRouteFoundError):
        await make_router(client).get_routes([START, END], BikeType.HYBRID)


@respx.mock
async def test_ors_unroutable_point_raises_no_route(client: httpx.AsyncClient) -> None:
    error = {"error": {"code": 2010, "message": "Could not find routable point"}}
    respx.post(directions_url()).mock(return_value=httpx.Response(404, json=error))
    with pytest.raises(NoRouteFoundError):
        await make_router(client).get_routes([START, END], BikeType.HYBRID)


@pytest.mark.parametrize(
    ("response", "error_type"),
    [
        (httpx.Response(403, json={"error": "Access denied"}), ExternalServiceError),
        (httpx.Response(429, json={"error": "Rate limit exceeded"}), RateLimitedError),
        (httpx.Response(503, text="Service Unavailable"), ExternalServiceError),
        (httpx.Response(200, json={"unexpected": True}), ExternalServiceError),
        (httpx.Response(200, text="<html>not json</html>"), ExternalServiceError),
        (
            httpx.Response(400, json={"error": {"code": 2003, "message": "bad"}}),
            ExternalServiceError,
        ),
    ],
)
@respx.mock
async def test_ors_failures_raise_domain_errors(
    client: httpx.AsyncClient, response: httpx.Response, error_type: type[Exception]
) -> None:
    respx.post(directions_url()).mock(return_value=response)
    with pytest.raises(error_type):
        await make_router(client).get_routes([START, END], BikeType.HYBRID)


@respx.mock
async def test_ors_network_error_raises_external_service_error(client: httpx.AsyncClient) -> None:
    respx.post(directions_url()).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(ExternalServiceError, match="Could not reach"):
        await make_router(client).get_routes([START, END], BikeType.HYBRID)


async def test_ors_without_api_key_raises_configuration_error(client: httpx.AsyncClient) -> None:
    with pytest.raises(ConfigurationError):
        await make_router(client, api_key="").get_routes([START, END], BikeType.HYBRID)


# --- Geocoding (ORS / Pelias) -----------------------------------------------------------------

AUTOCOMPLETE_URL = f"{ORS_BASE}/geocode/autocomplete"
SEARCH_URL = f"{ORS_BASE}/geocode/search"


def make_geocoder(client: httpx.AsyncClient, api_key: str = "secret") -> OpenRouteServiceGeocoder:
    return OpenRouteServiceGeocoder(client, ORS_BASE, api_key)


@respx.mock
async def test_geocode_uses_search_and_parses_result(client: httpx.AsyncClient) -> None:
    route = respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(200, json=pelias_response((WATERLOO_LABEL, 43.4643, -80.5204)))
    )

    location = await make_geocoder(client).geocode("Waterloo")

    assert location.coordinate == Coordinate(43.4643, -80.5204)
    assert location.display_name == WATERLOO_LABEL
    request = route.calls.last.request
    assert request.headers["Authorization"] == "secret"
    assert request.url.params["text"] == "Waterloo"


@respx.mock
async def test_geocode_no_results_raises_location_not_found(client: httpx.AsyncClient) -> None:
    respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=pelias_response()))
    with pytest.raises(LocationNotFoundError, match="Atlantis"):
        await make_geocoder(client).geocode("Atlantis")


@respx.mock
async def test_autocomplete_passes_focus_and_limit(client: httpx.AsyncClient) -> None:
    places = [(f"Place {i}, Waterloo, ON, Canada", 43.0 + i / 100, -80.0) for i in range(5)]
    route = respx.get(AUTOCOMPLETE_URL).mock(
        return_value=httpx.Response(200, json=pelias_response(*places))
    )

    suggestions = await make_geocoder(client).autocomplete(
        "Pla", focus=Coordinate(43.46, -80.52), limit=5
    )

    assert [s.display_name for s in suggestions] == [p[0] for p in places]
    params = route.calls.last.request.url.params
    assert params["text"] == "Pla"
    assert params["size"] == "5"
    assert params["focus.point.lat"] == "43.46"
    assert params["focus.point.lon"] == "-80.52"


@respx.mock
async def test_autocomplete_falls_back_to_search_when_empty(client: httpx.AsyncClient) -> None:
    """Addresses whose house number is unmapped return nothing from autocomplete."""
    autocomplete = respx.get(AUTOCOMPLETE_URL).mock(
        return_value=httpx.Response(200, json=pelias_response())
    )
    search = respx.get(SEARCH_URL).mock(
        return_value=httpx.Response(
            200, json=pelias_response(("Randall Drive, Waterloo, ON, Canada", 43.47, -80.53))
        )
    )

    [suggestion] = await make_geocoder(client).autocomplete("12 randall drive waterloo")

    assert suggestion.display_name == "Randall Drive, Waterloo, ON, Canada"
    assert autocomplete.called and search.called


@respx.mock
async def test_autocomplete_does_not_fall_back_when_results_exist(
    client: httpx.AsyncClient,
) -> None:
    respx.get(AUTOCOMPLETE_URL).mock(
        return_value=httpx.Response(
            200, json=pelias_response(("330 Phillip Street, Waterloo, ON, Canada", 43.47, -80.53))
        )
    )
    search = respx.get(SEARCH_URL).mock(return_value=httpx.Response(200, json=pelias_response()))

    suggestions = await make_geocoder(client).autocomplete("330 phillip")

    assert len(suggestions) == 1
    assert not search.called


@respx.mock
async def test_geocoder_rejected_key(client: httpx.AsyncClient) -> None:
    respx.get(AUTOCOMPLETE_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(ExternalServiceError, match="API key"):
        await make_geocoder(client).autocomplete("Cambridge")


@respx.mock
async def test_geocoder_network_failure(client: httpx.AsyncClient) -> None:
    respx.get(AUTOCOMPLETE_URL).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(ExternalServiceError, match="Could not reach"):
        await make_geocoder(client).autocomplete("Cambridge")


async def test_geocoder_without_api_key_raises_configuration_error(
    client: httpx.AsyncClient,
) -> None:
    with pytest.raises(ConfigurationError):
        await make_geocoder(client, api_key="").autocomplete("Waterloo")
