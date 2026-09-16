import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.models import RouteRecord, RouteSearch
from app.domain import BikeType, Coordinate, Location, TripMode

MIN_TARGET_KM = 2.0
MAX_TARGET_KM = 150.0


def _round(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


class Preferences(BaseModel):
    """Relative importance of each factor. Weights are normalised to sum to 1."""

    distance_weight: float = Field(ge=0, le=1)
    elevation_weight: float = Field(ge=0, le=1)
    safety_weight: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def at_least_one_weight(self) -> Self:
        if self.distance_weight + self.elevation_weight + self.safety_weight <= 0:
            raise ValueError("At least one preference weight must be greater than zero")
        return self


class LocationInput(BaseModel):
    """A place picked from autocomplete (label + coordinates) or free text to geocode."""

    model_config = ConfigDict(str_strip_whitespace=True)

    label: str = Field(min_length=2, max_length=200, examples=["Waterloo, ON, Canada"])
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def both_or_neither_coordinate(self) -> Self:
        if (self.lat is None) != (self.lon is None):
            raise ValueError("Provide both lat and lon, or neither")
        return self

    @property
    def coordinate(self) -> Coordinate | None:
        if self.lat is None or self.lon is None:
            return None
        return Coordinate(lat=self.lat, lon=self.lon)


class RouteRequest(BaseModel):
    mode: TripMode = TripMode.LOOP
    start: LocationInput
    destination: LocationInput | None = None
    target_distance_km: float | None = Field(default=None, ge=MIN_TARGET_KM, le=MAX_TARGET_KM)
    bike_type: BikeType = BikeType.HYBRID
    preferences: Preferences | None = None

    @model_validator(mode="after")
    def fields_required_by_mode(self) -> Self:
        needs_target = self.mode in (TripMode.LOOP, TripMode.DISTANCE_GOAL)
        needs_destination = self.mode in (TripMode.DISTANCE_GOAL, TripMode.POINT_TO_POINT)
        if needs_target and self.target_distance_km is None:
            raise ValueError("A target distance is required for this trip type")
        if needs_destination and self.destination is None:
            raise ValueError("A destination is required for this trip type")
        if self.mode is TripMode.LOOP:
            self.destination = None
        if self.mode is TripMode.POINT_TO_POINT:
            self.target_distance_km = None
        return self


class LocationResponse(BaseModel):
    query: str
    display_name: str
    lat: float
    lon: float

    @classmethod
    def from_location(cls, location: Location) -> Self:
        return cls(
            query=location.query,
            display_name=location.display_name,
            lat=location.coordinate.lat,
            lon=location.coordinate.lon,
        )


class AutocompleteResponse(BaseModel):
    suggestions: list[LocationResponse]


class RouteResponse(BaseModel):
    id: uuid.UUID
    rank: int
    distance_km: float
    elevation_gain_m: float | None
    duration_min: float
    safety_score: float | None = Field(
        description="Estimated proxy based on way types, not an authoritative safety rating"
    )
    distance_score: float
    elevation_score: float | None
    overall_score: float
    repeated_share: float = Field(description="Share of the ride that doubles back on itself")
    summary: str
    highlights: list[str]
    way_type_shares: dict[str, float]
    geometry: list[list[float]] = Field(description="[[lat, lon], ...]")
    elevation_profile: list[list[float]] = Field(description="[[distance_km, elevation_m], ...]")

    @classmethod
    def from_record(cls, record: RouteRecord) -> Self:
        return cls(
            id=record.id,
            rank=record.rank,
            distance_km=round(record.distance_km, 2),
            elevation_gain_m=_round(record.elevation_gain_m, 0),
            duration_min=round(record.duration_min),
            safety_score=_round(record.safety_score),
            distance_score=round(record.distance_score, 1),
            elevation_score=_round(record.elevation_score),
            overall_score=round(record.overall_score, 1),
            repeated_share=round(record.repeated_share, 3),
            summary=record.summary,
            highlights=record.highlights,
            way_type_shares={k: round(v, 3) for k, v in record.way_type_shares.items()},
            geometry=[[round(lat, 5), round(lon, 5)] for lat, lon in record.geometry],
            elevation_profile=[[round(d, 3), round(e, 1)] for d, e in record.elevation_profile],
        )


class SearchContext(BaseModel):
    search_id: uuid.UUID
    created_at: datetime
    mode: TripMode
    bike_type: BikeType
    target_distance_km: float | None
    start: LocationResponse
    destination: LocationResponse | None
    preferences: Preferences
    warnings: list[str]

    @classmethod
    def from_record(cls, search: RouteSearch) -> Self:
        destination = None
        if search.destination_lat is not None and search.destination_lon is not None:
            destination = LocationResponse(
                query=search.destination_query or "",
                display_name=search.destination_name or "",
                lat=search.destination_lat,
                lon=search.destination_lon,
            )
        return cls(
            search_id=search.id,
            created_at=search.created_at,
            mode=TripMode(search.mode),
            bike_type=BikeType(search.bike_type),
            target_distance_km=search.target_distance_km,
            start=LocationResponse(
                query=search.start_query,
                display_name=search.start_name,
                lat=search.start_lat,
                lon=search.start_lon,
            ),
            destination=destination,
            preferences=Preferences(
                distance_weight=round(search.distance_weight, 3),
                elevation_weight=round(search.elevation_weight, 3),
                safety_weight=round(search.safety_weight, 3),
            ),
            warnings=search.warnings,
        )


class RouteSearchResponse(SearchContext):
    routes: list[RouteResponse]

    @classmethod
    def from_record(cls, search: RouteSearch) -> Self:
        context = SearchContext.from_record(search)
        return cls(
            **context.model_dump(),
            routes=[RouteResponse.from_record(route) for route in search.routes],
        )


class RouteDetailResponse(BaseModel):
    route: RouteResponse
    search: SearchContext


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, object]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
