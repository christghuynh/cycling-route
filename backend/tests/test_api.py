import json
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.domain import Coordinate
from app.main import create_app
from app.services.geometry import path_length_m
from tests.factories import (
    CAMBRIDGE,
    WATERLOO,
    WATERLOO_LABEL,
    default_ors_response,
    ors_route,
    pelias_response,
)

ORS = "https://ors.test"
DIRECTIONS_URL = f"{ORS}/v2/directions/cycling-regular/json"
ROAD_DIRECTIONS_URL = f"{ORS}/v2/directions/cycling-road/json"
AUTOCOMPLETE_URL = f"{ORS}/geocode/autocomplete"
SEARCH_URL = f"{ORS}/geocode/search"

HOME = {"label": "Waterloo, ON, Canada", "lat": 43.4643, "lon": -80.5204}
PARK = {"label": "Waterloo Park, ON, Canada", "lat": 43.4666, "lon": -80.5288}

POINT_TO_POINT_REQUEST = {
    "mode": "point_to_point",
    "start": {"label": "Waterloo, Ontario"},
    "destination": {"label": "Cambridge, Ontario"},
    "preferences": {"distance_weight": 0.4, "elevation_weight": 0.3, "safety_weight": 0.3},
}
LOOP_REQUEST = {"mode": "loop", "start": HOME, "target_distance_km": 30, "bike_type": "road"}


def geocode_response(request: httpx.Request) -> httpx.Response:
    text = request.url.params["text"].lower()
    if "waterloo" in text:
        return httpx.Response(200, json=pelias_response(WATERLOO))
    if "cambridge" in text:
        return httpx.Response(200, json=pelias_response(CAMBRIDGE))
    return httpx.Response(200, json=pelias_response())


def route_through_waypoints(request: httpx.Request) -> httpx.Response:
    """Fake ORS: follow the requested waypoints in straight lines, 1.25x longer on 'roads'."""
    body = json.loads(request.content)
    points = [(lat, lon) for lon, lat in body["coordinates"]]
    distance = path_length_m([Coordinate(lat, lon) for lat, lon in points]) * 1.25
    route = ors_route(points, distance, distance / 5, {6: distance * 0.6, 3: distance * 0.4})
    return httpx.Response(200, json={"routes": [route]})


def mock_point_to_point(api_mock: respx.MockRouter, ors: httpx.Response | None = None) -> None:
    api_mock.get(SEARCH_URL).mock(side_effect=geocode_response)
    api_mock.post(DIRECTIONS_URL).mock(
        return_value=ors or httpx.Response(200, json=default_ors_response())
    )


def assert_error(response: httpx.Response, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert body["error"]["code"] == code
    assert body["error"]["message"]
    return body


# --- Loops and target-distance rides ----------------------------------------------------------


def test_loop_returns_ranked_rides_from_home_near_target(
    client: TestClient, api_mock: respx.MockRouter
) -> None:
    api_mock.post(ROAD_DIRECTIONS_URL).mock(side_effect=route_through_waypoints)

    response = client.post("/api/routes", json=LOOP_REQUEST)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["mode"] == "loop"
    assert body["bike_type"] == "road"
    assert body["target_distance_km"] == 30
    assert body["destination"] is None
    assert body["start"]["display_name"] == "Waterloo, ON, Canada"
    # The start came from autocomplete with coordinates, so nothing was geocoded.
    assert all("/geocode/" not in str(call.request.url) for call in api_mock.calls)

    routes = body["routes"]
    assert 1 <= len(routes) <= 4
    assert [route["rank"] for route in routes] == list(range(1, len(routes) + 1))
    for route in routes:
        assert route["geometry"][0] == [HOME["lat"], HOME["lon"]]
        assert route["geometry"][-1] == [HOME["lat"], HOME["lon"]]
        assert route["distance_km"] == pytest.approx(30, rel=0.1)
        assert route["elevation_gain_m"] is not None
        assert route["safety_score"] is not None


def test_distance_goal_finishes_at_destination(
    client: TestClient, api_mock: respx.MockRouter
) -> None:
    api_mock.post(DIRECTIONS_URL).mock(side_effect=route_through_waypoints)
    request = {
        "mode": "distance_goal",
        "start": HOME,
        "destination": PARK,
        "target_distance_km": 20,
    }

    response = client.post("/api/routes", json=request)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["destination"]["display_name"] == PARK["label"]
    for route in body["routes"]:
        assert route["geometry"][-1] == [PARK["lat"], PARK["lon"]]
        assert route["distance_km"] == pytest.approx(20, rel=0.1)


def test_distance_goal_too_short_for_destination(
    client: TestClient, api_mock: respx.MockRouter
) -> None:
    far = {"label": "Guelph, ON", "lat": 43.5448, "lon": -80.2482}  # ~24 km away
    request = {"mode": "distance_goal", "start": HOME, "destination": far, "target_distance_km": 20}
    assert_error(client.post("/api/routes", json=request), 422, "invalid_trip")
    assert not api_mock.calls


def test_generated_route_can_be_fetched_by_id(
    client: TestClient, api_mock: respx.MockRouter
) -> None:
    api_mock.post(ROAD_DIRECTIONS_URL).mock(side_effect=route_through_waypoints)
    created = client.post("/api/routes", json=LOOP_REQUEST).json()
    route_id = created["routes"][0]["id"]

    response = client.get(f"/api/routes/{route_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == created["routes"][0]
    assert body["search"]["search_id"] == created["search_id"]
    assert body["search"]["mode"] == "loop"


# --- Point to point ---------------------------------------------------------------------------


def test_point_to_point_geocodes_text_and_ranks_routes(
    client: TestClient, api_mock: respx.MockRouter
) -> None:
    mock_point_to_point(api_mock)

    response = client.post("/api/routes", json=POINT_TO_POINT_REQUEST)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["start"]["display_name"] == WATERLOO_LABEL
    assert body["target_distance_km"] is None
    routes = body["routes"]
    assert [route["rank"] for route in routes] == [1, 2]
    # With these weights the cycleway-heavy route beats the slightly shorter road route.
    assert routes[0]["distance_km"] == 24.0


def test_default_preferences_are_used_when_omitted(
    client: TestClient, api_mock: respx.MockRouter
) -> None:
    api_mock.post(ROAD_DIRECTIONS_URL).mock(side_effect=route_through_waypoints)
    body = client.post("/api/routes", json=LOOP_REQUEST).json()
    assert body["preferences"] == {
        "distance_weight": 0.5,
        "elevation_weight": 0.2,
        "safety_weight": 0.3,
    }


def test_preferences_are_normalised(client: TestClient, api_mock: respx.MockRouter) -> None:
    mock_point_to_point(api_mock)
    request = {
        **POINT_TO_POINT_REQUEST,
        "preferences": {"distance_weight": 1, "elevation_weight": 0.5, "safety_weight": 0.5},
    }
    body = client.post("/api/routes", json=request).json()
    assert body["preferences"] == {
        "distance_weight": 0.5,
        "elevation_weight": 0.25,
        "safety_weight": 0.25,
    }


# --- Autocomplete -----------------------------------------------------------------------------


def test_autocomplete_returns_suggestions(client: TestClient, api_mock: respx.MockRouter) -> None:
    route = api_mock.get(AUTOCOMPLETE_URL).mock(
        return_value=httpx.Response(
            200,
            json=pelias_response(WATERLOO, ("Waterloo, IA, USA", 42.4928, -92.3426)),
        )
    )

    response = client.get(
        "/api/locations/autocomplete", params={"q": "Waterl", "focus_lat": 43.4, "focus_lon": -80.5}
    )

    assert response.status_code == 200
    assert [s["display_name"] for s in response.json()["suggestions"]] == [
        WATERLOO_LABEL,
        "Waterloo, IA, USA",
    ]
    assert route.calls.last.request.url.params["focus.point.lat"] == "43.4"


def test_autocomplete_requires_three_characters(
    client: TestClient, api_mock: respx.MockRouter
) -> None:
    assert_error(
        client.get("/api/locations/autocomplete", params={"q": "Wa"}), 422, "invalid_request"
    )
    assert not api_mock.calls


# --- Invalid requests -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"mode": "loop", "start": HOME},  # no target distance
        {"mode": "point_to_point", "start": HOME},  # no destination
        {"mode": "distance_goal", "start": HOME, "target_distance_km": 20},  # no destination
        {**LOOP_REQUEST, "target_distance_km": 500},
        {**LOOP_REQUEST, "bike_type": "unicycle"},
        {**LOOP_REQUEST, "mode": "teleport"},
        {**LOOP_REQUEST, "start": {"label": "Home", "lat": 43.4}},  # lat without lon
        {**LOOP_REQUEST, "start": {"label": ""}},
        {
            **LOOP_REQUEST,
            "preferences": {"distance_weight": 0, "elevation_weight": 0, "safety_weight": 0},
        },
    ],
)
def test_invalid_requests_are_rejected(
    client: TestClient, api_mock: respx.MockRouter, payload: dict[str, Any]
) -> None:
    body = assert_error(client.post("/api/routes", json=payload), 422, "invalid_request")
    assert body["error"]["details"]
    assert not api_mock.calls, "No external API should be called for invalid input"


def test_malformed_json_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/routes", content="{not json", headers={"Content-Type": "application/json"}
    )
    assert_error(response, 422, "invalid_request")


# --- External failures ------------------------------------------------------------------------


def test_unknown_location(client: TestClient, api_mock: respx.MockRouter) -> None:
    mock_point_to_point(api_mock)
    request = {**POINT_TO_POINT_REQUEST, "destination": {"label": "Atlantis"}}
    body = assert_error(client.post("/api/routes", json=request), 422, "location_not_found")
    assert "Atlantis" in body["error"]["message"]


def test_geocoding_service_failure(client: TestClient, api_mock: respx.MockRouter) -> None:
    api_mock.get(SEARCH_URL).mock(side_effect=httpx.ConnectTimeout("timed out"))
    response = client.post("/api/routes", json=POINT_TO_POINT_REQUEST)
    assert_error(response, 502, "external_service_error")


def test_routing_service_failure(client: TestClient, api_mock: respx.MockRouter) -> None:
    api_mock.post(ROAD_DIRECTIONS_URL).mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )
    body = assert_error(
        client.post("/api/routes", json=LOOP_REQUEST), 502, "external_service_error"
    )
    assert "Internal Server Error" not in body["error"]["message"]


def test_routing_rate_limit(client: TestClient, api_mock: respx.MockRouter) -> None:
    api_mock.post(ROAD_DIRECTIONS_URL).mock(
        return_value=httpx.Response(429, json={"error": "Rate limit exceeded"})
    )
    assert_error(client.post("/api/routes", json=LOOP_REQUEST), 503, "rate_limited")


def test_invalid_routing_response(client: TestClient, api_mock: respx.MockRouter) -> None:
    mock_point_to_point(api_mock, ors=httpx.Response(200, json={"routes": [{"geometry": 42}]}))
    response = client.post("/api/routes", json=POINT_TO_POINT_REQUEST)
    assert_error(response, 502, "external_service_error")


def test_empty_route_response(client: TestClient, api_mock: respx.MockRouter) -> None:
    mock_point_to_point(api_mock, ors=httpx.Response(200, json={"routes": []}))
    response = client.post("/api/routes", json=POINT_TO_POINT_REQUEST)
    assert_error(response, 404, "no_route_found")


def test_loop_with_no_routable_direction(client: TestClient, api_mock: respx.MockRouter) -> None:
    error = {"error": {"code": 2010, "message": "Could not find routable point"}}
    api_mock.post(ROAD_DIRECTIONS_URL).mock(return_value=httpx.Response(404, json=error))
    assert_error(client.post("/api/routes", json=LOOP_REQUEST), 404, "no_route_found")


def test_missing_api_key(settings: Settings, api_mock: respx.MockRouter) -> None:
    settings.ors_api_key = ""
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/routes", json=LOOP_REQUEST)
    assert_error(response, 503, "service_not_configured")


def test_database_failure_when_saving(
    client: TestClient, api_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    api_mock.post(ROAD_DIRECTIONS_URL).mock(side_effect=route_through_waypoints)

    async def failing_commit(self: AsyncSession) -> None:
        raise OperationalError("INSERT", {}, Exception("database is down"))

    monkeypatch.setattr(AsyncSession, "commit", failing_commit)
    body = assert_error(client.post("/api/routes", json=LOOP_REQUEST), 503, "database_error")
    assert "database is down" not in body["error"]["message"]


# --- Rate limiting ----------------------------------------------------------------------------


def test_route_generation_is_rate_limited_per_client(
    settings: Settings, api_mock: respx.MockRouter
) -> None:
    settings.route_requests_per_hour = 2
    api_mock.post(ROAD_DIRECTIONS_URL).mock(side_effect=route_through_waypoints)
    rider = {"x-forwarded-for": "203.0.113.7"}

    with TestClient(create_app(settings)) as client:
        for _ in range(2):
            assert client.post("/api/routes", json=LOOP_REQUEST, headers=rider).status_code == 201

        response = client.post("/api/routes", json=LOOP_REQUEST, headers=rider)
        assert_error(response, 429, "too_many_requests")
        assert response.headers["Retry-After"]

        # Another rider is unaffected.
        other = {"x-forwarded-for": "198.51.100.9"}
        assert client.post("/api/routes", json=LOOP_REQUEST, headers=other).status_code == 201


def test_autocomplete_has_its_own_looser_limit(
    settings: Settings, api_mock: respx.MockRouter
) -> None:
    settings.route_requests_per_hour = 1
    settings.autocomplete_requests_per_hour = 5
    api_mock.get(AUTOCOMPLETE_URL).mock(side_effect=geocode_response)
    api_mock.post(ROAD_DIRECTIONS_URL).mock(side_effect=route_through_waypoints)
    rider = {"x-forwarded-for": "203.0.113.7"}

    with TestClient(create_app(settings)) as client:
        client.post("/api/routes", json=LOOP_REQUEST, headers=rider)
        # Searching is now exhausted, but typing still works.
        for _ in range(5):
            response = client.get(
                "/api/locations/autocomplete", params={"q": "waterloo"}, headers=rider
            )
            assert response.status_code == 200
        assert_error(
            client.get("/api/locations/autocomplete", params={"q": "waterloo"}, headers=rider),
            429,
            "too_many_requests",
        )


def test_rate_limiting_can_be_disabled(settings: Settings, api_mock: respx.MockRouter) -> None:
    settings.rate_limit_enabled = False
    settings.route_requests_per_hour = 1
    api_mock.post(ROAD_DIRECTIONS_URL).mock(side_effect=route_through_waypoints)

    with TestClient(create_app(settings)) as client:
        for _ in range(3):
            assert client.post("/api/routes", json=LOOP_REQUEST).status_code == 201


# --- Other endpoints --------------------------------------------------------------------------


def test_unknown_route_id_returns_404(client: TestClient) -> None:
    response = client.get("/api/routes/00000000-0000-0000-0000-000000000000")
    assert_error(response, 404, "route_not_found")


def test_invalid_route_id_returns_422(client: TestClient) -> None:
    assert_error(client.get("/api/routes/not-a-uuid"), 422, "invalid_request")


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
