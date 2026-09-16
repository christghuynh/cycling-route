"""FallbackGeocoder: Photon first, OpenRouteService only when Photon cannot answer."""

import pytest

from app.core.errors import ExternalServiceError, LocationNotFoundError, QuotaExceededError
from app.domain import Coordinate, Location
from app.services.geocoding import FallbackGeocoder

HERE = Location("waterloo", "Waterloo, ON, Canada", Coordinate(43.46, -80.52))


class FakeGeocoder:
    def __init__(self, result: list[Location] | Exception) -> None:
        self.result = result
        self.calls = 0

    async def geocode(self, query: str) -> Location:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        if not self.result:
            raise LocationNotFoundError(f"Could not find a location matching '{query}'.")
        return self.result[0]

    async def autocomplete(
        self, text: str, focus: Coordinate | None = None, limit: int = 5
    ) -> list[Location]:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


async def test_suggestions_come_from_the_primary_when_it_answers() -> None:
    primary, fallback = FakeGeocoder([HERE]), FakeGeocoder([HERE])
    assert await FallbackGeocoder(primary, fallback).autocomplete("waterloo") == [HERE]
    assert fallback.calls == 0


async def test_suggestions_fall_back_when_the_primary_fails() -> None:
    primary = FakeGeocoder(ExternalServiceError("geocoding", "Photon is down"))
    fallback = FakeGeocoder([HERE])
    assert await FallbackGeocoder(primary, fallback).autocomplete("waterloo") == [HERE]
    assert fallback.calls == 1


async def test_empty_suggestions_do_not_spend_the_fallbacks_quota() -> None:
    """A typo returning nothing is an answer, not a failure."""
    primary, fallback = FakeGeocoder([]), FakeGeocoder([HERE])
    assert await FallbackGeocoder(primary, fallback).autocomplete("wxqzv") == []
    assert fallback.calls == 0


async def test_lookup_falls_back_when_the_primary_finds_nothing() -> None:
    primary, fallback = FakeGeocoder([]), FakeGeocoder([HERE])
    assert await FallbackGeocoder(primary, fallback).geocode("waterloo") == HERE
    assert fallback.calls == 1


async def test_lookup_falls_back_when_the_primary_fails() -> None:
    primary = FakeGeocoder(ExternalServiceError("geocoding", "Photon is down"))
    fallback = FakeGeocoder([HERE])
    assert await FallbackGeocoder(primary, fallback).geocode("waterloo") == HERE


async def test_fallback_errors_still_reach_the_caller() -> None:
    primary = FakeGeocoder(ExternalServiceError("geocoding", "Photon is down"))
    fallback = FakeGeocoder(QuotaExceededError("geocoding", "Quota used up"))
    with pytest.raises(QuotaExceededError):
        await FallbackGeocoder(primary, fallback).autocomplete("waterloo")
