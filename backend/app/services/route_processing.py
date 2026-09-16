"""Turn raw candidate routes into measured, provider-neutral route metrics."""

from collections.abc import Sequence

from app.domain import CandidateRoute, Coordinate, ElevationPoint, RouteMetrics
from app.services.geometry import cumulative_distances_m, resample_path
from app.services.safety import estimate_safety_score

# Grid used to compare where routes go: ~30 m cells at mid latitudes.
CELL_DEG_LAT = 0.0003
CELL_DEG_LON = 0.0004
CELL_SAMPLE_SPACING_M = 25.0
# A cell revisited after riding at least this far counts as repeated road, so that dense
# sampling along a single pass is not mistaken for backtracking.
REVISIT_MIN_GAP_M = 300.0
MAX_PROFILE_POINTS = 200


def calculate_elevation_gain(elevations: Sequence[float], noise_threshold_m: float = 0.0) -> float:
    """Total climbing in metres: the sum of positive elevation changes along a route.

    Small fluctuations are ignored using a hysteresis threshold: a climb is only counted once
    the elevation rises at least `noise_threshold_m` above the lowest point seen since the last
    counted climb. Any descent lowers that reference point, so a genuine climb that follows a
    dip is measured from the bottom of the dip. With a threshold of 0 this is exactly the sum of
    positive differences between consecutive samples.
    """
    if noise_threshold_m < 0:
        raise ValueError("noise_threshold_m must be non-negative")
    if len(elevations) < 2:
        return 0.0

    gain = 0.0
    reference = elevations[0]
    for elevation in elevations[1:]:
        if elevation < reference:
            reference = elevation
        elif elevation > reference and elevation - reference >= noise_threshold_m:
            gain += elevation - reference
            reference = elevation
    return gain


def calculate_way_type_shares(way_type_distances_m: dict[str, float]) -> dict[str, float]:
    """Convert metres per way type into fractions of the route (summing to 1)."""
    total = sum(distance for distance in way_type_distances_m.values() if distance > 0)
    if total <= 0:
        return {}
    return {
        way_type: distance / total
        for way_type, distance in way_type_distances_m.items()
        if distance > 0
    }


def estimate_duration_min(distance_km: float, speed_kmh: float) -> float:
    return distance_km / speed_kmh * 60


def _cell(point: Coordinate) -> tuple[int, int]:
    return round(point.lat / CELL_DEG_LAT), round(point.lon / CELL_DEG_LON)


def route_cells(path: list[Coordinate]) -> set[tuple[int, int]]:
    samples = resample_path(path, CELL_SAMPLE_SPACING_M, max_samples=20_000)
    return {_cell(point) for _, point in samples}


def calculate_repeated_share(path: list[Coordinate]) -> float:
    """Fraction of the route that rides over ground already covered earlier in the ride.

    Out-and-back sections (riding to a dead end and returning the same way) score high; a clean
    loop scores close to 0.
    """
    samples = resample_path(path, CELL_SAMPLE_SPACING_M, max_samples=20_000)
    if len(samples) < 2:
        return 0.0
    first_visit: dict[tuple[int, int], float] = {}
    repeated = 0
    for distance, point in samples:
        cell = _cell(point)
        visited_at = first_visit.setdefault(cell, distance)
        if distance - visited_at >= REVISIT_MIN_GAP_M:
            repeated += 1
    return repeated / len(samples)


def route_overlap(a: set[tuple[int, int]], b: set[tuple[int, int]]) -> float:
    """Share of the smaller route's ground that the other route also covers (0-1)."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _elevation_profile(
    distances_m: list[float], elevations: Sequence[float]
) -> list[ElevationPoint]:
    step = max(1, len(elevations) // MAX_PROFILE_POINTS)
    indices = list(range(0, len(elevations), step))
    if indices[-1] != len(elevations) - 1:
        indices.append(len(elevations) - 1)
    return [
        ElevationPoint(distance_km=distances_m[i] / 1000, elevation_m=elevations[i])
        for i in indices
    ]


def build_route_metrics(
    candidate: CandidateRoute,
    *,
    noise_threshold_m: float,
    default_speed_kmh: float,
) -> RouteMetrics:
    """Measure a candidate route: distance, duration, climbing, way types, backtracking."""
    elevations = candidate.elevations
    if elevations is not None and len(elevations) != len(candidate.geometry):
        raise ValueError("Expected one elevation per geometry point")

    distances_m = cumulative_distances_m(candidate.geometry)
    if candidate.distance_m and candidate.distance_m > 0:
        distance_km = candidate.distance_m / 1000
    else:
        distance_km = distances_m[-1] / 1000 if distances_m else 0.0

    if candidate.duration_s and candidate.duration_s > 0:
        duration_min = candidate.duration_s / 60
    else:
        duration_min = estimate_duration_min(distance_km, default_speed_kmh)

    elevation_gain_m: float | None = None
    profile: list[ElevationPoint] = []
    if elevations:
        elevation_gain_m = calculate_elevation_gain(elevations, noise_threshold_m)
        profile = _elevation_profile(distances_m, elevations)

    shares = calculate_way_type_shares(candidate.way_type_distances_m)
    return RouteMetrics(
        geometry=candidate.geometry,
        distance_km=distance_km,
        duration_min=duration_min,
        elevation_gain_m=elevation_gain_m,
        elevation_profile=profile,
        way_type_shares=shares,
        safety_score=estimate_safety_score(shares),
        repeated_share=calculate_repeated_share(candidate.geometry),
    )
