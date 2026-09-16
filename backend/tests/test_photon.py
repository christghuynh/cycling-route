"""Tests for the Photon geocoder: request shape, labels, and duplicate collapsing."""

import httpx
import pytest
import respx

from app.core.errors import ExternalServiceError, LocationNotFoundError
from app.domain import Coordinate
from app.services.photon import PhotonGeocoder
from tests.factories import (
    PHOTON_WATERLOO,
    PHOTON_WATERLOO_LABEL,
    photon_place,
    photon_response,
)

WATERLOO = PHOTON_WATERLOO
WATERLOO_LABEL = PHOTON_WATERLOO_LABEL


@pytest.fixture
async def client() -> httpx.AsyncClient:
    async with httpx.AsyncClient() as http_client:
        yield http_client


PHOTON_BASE = "https://photon.test"
PHOTON_URL = f"{PHOTON_BASE}/api"


def make_geocoder(client: httpx.AsyncClient) -> PhotonGeocoder:
    return PhotonGeocoder(client, PHOTON_BASE, "test-agent")


@respx.mock
async def test_geocode_result_is_parsed(client: httpx.AsyncClient) -> None:
    route = respx.get(PHOTON_URL).mock(
        return_value=httpx.Response(200, json=photon_response(WATERLOO))
    )

    location = await make_geocoder(client).geocode("Waterloo")

    assert location.coordinate == Coordinate(43.4643, -80.5204)
    assert location.display_name == WATERLOO_LABEL
    request = route.calls.last.request
    assert request.headers["User-Agent"] == "test-agent"
    assert request.url.params["q"] == "Waterloo"


@respx.mock
async def test_geocode_no_results_raises_location_not_found(client: httpx.AsyncClient) -> None:
    respx.get(PHOTON_URL).mock(return_value=httpx.Response(200, json=photon_response()))
    with pytest.raises(LocationNotFoundError, match="Atlantis"):
        await make_geocoder(client).geocode("Atlantis")


@respx.mock
async def test_street_addresses_are_labelled_with_house_number(
    client: httpx.AsyncClient,
) -> None:
    payload = photon_response(
        photon_place(
            43.4761,
            -80.5389,
            name="Tsujiri",
            housenumber="330",
            street="Phillip Street",
            city="Waterloo",
            state="Ontario",
            country="Canada",
        )
    )
    respx.get(PHOTON_URL).mock(return_value=httpx.Response(200, json=payload))

    [suggestion] = await make_geocoder(client).autocomplete("Tsujiri")

    assert suggestion.display_name == "Tsujiri, 330 Phillip Street, Waterloo, Ontario, Canada"


@respx.mock
async def test_businesses_at_one_address_collapse_into_a_single_suggestion(
    client: httpx.AsyncClient,
) -> None:
    address = {
        "housenumber": "330",
        "street": "Phillip Street",
        "city": "Waterloo",
        "state": "Ontario",
        "country": "Canada",
    }
    payload = photon_response(
        photon_place(43.4761, -80.5389, name="Tsujiri", **address),
        photon_place(43.4760, -80.5388, name="Popular Pizza", **address),
        photon_place(43.4762, -80.5389, name="Icon", **address),
        photon_place(43.4700, -80.5300, name="Waterloo Park", city="Waterloo", state="Ontario"),
    )
    respx.get(PHOTON_URL).mock(return_value=httpx.Response(200, json=payload))

    suggestions = await make_geocoder(client).autocomplete("330 phillip street")

    assert [s.display_name for s in suggestions] == [
        "330 Phillip Street, Waterloo, Ontario, Canada",
        "Waterloo Park, Waterloo, Ontario",
    ]


@respx.mock
async def test_autocomplete_passes_focus_and_limits_results(client: httpx.AsyncClient) -> None:
    places = [
        photon_place(43.0 + i / 100, -80.0, name=f"Place {i}", city="Waterloo") for i in range(8)
    ]
    route = respx.get(PHOTON_URL).mock(
        return_value=httpx.Response(200, json=photon_response(*places))
    )

    suggestions = await make_geocoder(client).autocomplete(
        "Pla", focus=Coordinate(43.46, -80.52), limit=5
    )

    assert [s.display_name for s in suggestions] == [f"Place {i}, Waterloo" for i in range(5)]
    params = route.calls.last.request.url.params
    assert params["q"] == "Pla"
    assert params["lat"] == "43.46"
    assert params["lon"] == "-80.52"


@respx.mock
async def test_geocoder_service_failure(client: httpx.AsyncClient) -> None:
    respx.get(PHOTON_URL).mock(return_value=httpx.Response(400, text="bad request"))
    with pytest.raises(ExternalServiceError):
        await make_geocoder(client).autocomplete("Cambridge")


@respx.mock
async def test_geocoder_network_failure(client: httpx.AsyncClient) -> None:
    respx.get(PHOTON_URL).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(ExternalServiceError, match="Could not reach"):
        await make_geocoder(client).autocomplete("Cambridge")
