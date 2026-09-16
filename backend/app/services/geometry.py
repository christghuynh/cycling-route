"""Pure geometry helpers: polyline decoding, distances, projection, and resampling."""

import math
from dataclasses import dataclass

from app.domain import Coordinate

EARTH_RADIUS_M = 6_371_008.8


@dataclass(frozen=True)
class DecodedPolyline:
    coordinates: list[Coordinate]
    elevations: list[float] | None


def decode_polyline(
    encoded: str, precision: int = 5, with_elevation: bool = False
) -> DecodedPolyline:
    """Decode a Google encoded polyline string.

    OpenRouteService extends the format with an optional third value per point: elevation,
    encoded with a factor of 100.
    """
    values_per_point = 3 if with_elevation else 2
    factor = 10**precision
    coordinates: list[Coordinate] = []
    elevations: list[float] = []
    totals = [0] * values_per_point
    index = 0

    while index < len(encoded):
        for position in range(values_per_point):
            result = shift = 0
            while True:
                if index >= len(encoded):
                    raise ValueError("Truncated polyline")
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            totals[position] += ~(result >> 1) if result & 1 else result >> 1
        coordinates.append(Coordinate(lat=totals[0] / factor, lon=totals[1] / factor))
        if with_elevation:
            elevations.append(totals[2] / 100)

    return DecodedPolyline(coordinates, elevations if with_elevation else None)


def haversine_m(a: Coordinate, b: Coordinate) -> float:
    """Great-circle distance between two coordinates in metres."""
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    d_lat = lat2 - lat1
    d_lon = math.radians(b.lon - a.lon)
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def path_length_m(path: list[Coordinate]) -> float:
    return sum(haversine_m(a, b) for a, b in zip(path, path[1:], strict=False))


def cumulative_distances_m(path: list[Coordinate]) -> list[float]:
    """Distance from the start of the path to each point."""
    distances = [0.0] * len(path)
    for i in range(1, len(path)):
        distances[i] = distances[i - 1] + haversine_m(path[i - 1], path[i])
    return distances


class LocalProjection:
    """Equirectangular projection to metres around an origin.

    Accurate to well under 1% within ~100 km, which is plenty for placing route waypoints.
    """

    def __init__(self, origin: Coordinate) -> None:
        self.origin = origin
        self._m_per_deg_lat = math.pi * EARTH_RADIUS_M / 180
        self._m_per_deg_lon = self._m_per_deg_lat * math.cos(math.radians(origin.lat))

    def to_xy(self, point: Coordinate) -> tuple[float, float]:
        return (
            (point.lon - self.origin.lon) * self._m_per_deg_lon,
            (point.lat - self.origin.lat) * self._m_per_deg_lat,
        )

    def to_coordinate(self, x: float, y: float) -> Coordinate:
        return Coordinate(
            lat=self.origin.lat + y / self._m_per_deg_lat,
            lon=self.origin.lon + x / self._m_per_deg_lon,
        )


def resample_path(
    path: list[Coordinate], spacing_m: float, max_samples: int
) -> list[tuple[float, Coordinate]]:
    """Return evenly spaced points along a path as (distance_from_start_m, coordinate) pairs.

    The spacing is widened when needed so that no more than `max_samples` points are returned.
    The first and last points of the path are always included.
    """
    if not path:
        return []
    total = path_length_m(path)
    if len(path) == 1 or total == 0:
        return [(0.0, path[0])]

    sample_count = min(max_samples, math.ceil(total / spacing_m) + 1)
    sample_count = max(sample_count, 2)
    step = total / (sample_count - 1)

    samples: list[tuple[float, Coordinate]] = [(0.0, path[0])]
    segment_start_distance = 0.0
    segment_index = 0
    for i in range(1, sample_count - 1):
        target = i * step
        # Advance to the segment that contains the target distance.
        while True:
            a, b = path[segment_index], path[segment_index + 1]
            segment_length = haversine_m(a, b)
            if segment_start_distance + segment_length >= target or (
                segment_index + 2 >= len(path)
            ):
                break
            segment_start_distance += segment_length
            segment_index += 1
        fraction = (target - segment_start_distance) / segment_length if segment_length else 0.0
        fraction = min(max(fraction, 0.0), 1.0)
        samples.append(
            (
                target,
                Coordinate(
                    lat=a.lat + (b.lat - a.lat) * fraction,
                    lon=a.lon + (b.lon - a.lon) * fraction,
                ),
            )
        )
    samples.append((total, path[-1]))
    return samples
