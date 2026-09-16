from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies import GeocoderDep
from app.api.errors import ERROR_RESPONSES
from app.api.limits import AutocompleteLimit
from app.domain import Coordinate
from app.schemas.route import AutocompleteResponse, LocationResponse

router = APIRouter(prefix="/api/locations", tags=["locations"])


@router.get(
    "/autocomplete",
    response_model=AutocompleteResponse,
    responses=ERROR_RESPONSES,
    dependencies=[AutocompleteLimit],
)
async def autocomplete(
    geocoder: GeocoderDep,
    q: Annotated[str, Query(min_length=3, max_length=200)],
    focus_lat: Annotated[float | None, Query(ge=-90, le=90)] = None,
    focus_lon: Annotated[float | None, Query(ge=-180, le=180)] = None,
) -> AutocompleteResponse:
    """Place suggestions while the user types, biased towards `focus` (e.g. the map centre)."""
    focus = (
        Coordinate(lat=focus_lat, lon=focus_lon)
        if focus_lat is not None and focus_lon is not None
        else None
    )
    locations = await geocoder.autocomplete(q.strip(), focus)
    return AutocompleteResponse(
        suggestions=[LocationResponse.from_location(location) for location in locations]
    )
