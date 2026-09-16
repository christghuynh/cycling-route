"""Provider-neutral internal data structures used by the route pipeline.

External API clients convert their responses into these types, so the processing and scoring
code never depends on a specific provider's payload format.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class Factor(StrEnum):
    """A route characteristic that contributes to the overall score."""

    DISTANCE = "distance"
    ELEVATION = "elevation"
    SAFETY = "safety"


class TripMode(StrEnum):
    """What the rider wants from the route."""

    LOOP = "loop"  # start and finish at the same place, ride a target distance
    DISTANCE_GOAL = "distance_goal"  # start and finish at different places, ride a target distance
    POINT_TO_POINT = "point_to_point"  # get from A to B


class BikeType(StrEnum):
    ROAD = "road"
    HYBRID = "hybrid"
    MOUNTAIN = "mountain"


@dataclass(frozen=True)
class Coordinate:
    lat: float
    lon: float


@dataclass(frozen=True)
class Location:
    query: str
    display_name: str
    coordinate: Coordinate


@dataclass(frozen=True)
class CandidateRoute:
    """A route as returned by a routing provider, before any processing."""

    geometry: list[Coordinate]
    distance_m: float | None
    duration_s: float | None
    # Metres travelled on each way type (e.g. "cycleway", "state_road"); empty if unknown.
    way_type_distances_m: dict[str, float] = field(default_factory=dict)
    # Terrain height for each geometry point, or None if the provider did not supply it.
    elevations: list[float] | None = None


@dataclass(frozen=True)
class ElevationPoint:
    distance_km: float
    elevation_m: float


@dataclass(frozen=True)
class RouteMetrics:
    """Measured facts about a route. `None` means the data was unavailable."""

    geometry: list[Coordinate]
    distance_km: float
    duration_min: float
    elevation_gain_m: float | None
    elevation_profile: list[ElevationPoint]
    way_type_shares: dict[str, float]
    safety_score: float | None
    # Share of the route that rides over road already covered earlier (out-and-back sections).
    repeated_share: float = 0.0


@dataclass(frozen=True)
class ComponentScores:
    distance: float
    elevation: float | None
    safety: float | None
    overall: float


@dataclass(frozen=True)
class ScoredRoute:
    rank: int
    metrics: RouteMetrics
    scores: ComponentScores
    summary: str
    highlights: list[str]


@dataclass(frozen=True)
class TripRequest:
    mode: TripMode
    start: Location
    destination: Location | None
    target_distance_km: float | None
    bike_type: BikeType


@dataclass(frozen=True)
class RoutePlan:
    trip: TripRequest
    routes: list[ScoredRoute]
    warnings: list[str]
