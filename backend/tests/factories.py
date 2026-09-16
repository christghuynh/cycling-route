"""Builders for fake external API payloads and domain objects used across tests."""

from typing import Any

from app.domain import Coordinate, RouteMetrics


def _encode_value(delta: int, output: list[str]) -> None:
    value = ~(delta << 1) if delta < 0 else delta << 1
    while value >= 0x20:
        output.append(chr((0x20 | (value & 0x1F)) + 63))
        value >>= 5
    output.append(chr(value + 63))


def encode_polyline(
    points: list[tuple[float, float]], elevations: list[float] | None = None
) -> str:
    """Encode (lat, lon) pairs, optionally with ORS-style elevation (test helper)."""
    output: list[str] = []
    previous = [0, 0, 0]
    for index, (lat, lon) in enumerate(points):
        values = [round(lat * 1e5), round(lon * 1e5)]
        if elevations is not None:
            values.append(round(elevations[index] * 100))
        for position, value in enumerate(values):
            _encode_value(value - previous[position], output)
            previous[position] = value
    return "".join(output)


def pelias_response(*places: tuple[str, float, float]) -> dict[str, Any]:
    """ORS/Pelias geocoding response for (label, lat, lon) places."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {"label": label, "country": "Canada"},
            }
            for label, lat, lon in places
        ],
    }


WATERLOO_LABEL = "Waterloo, ON, Canada"
CAMBRIDGE_LABEL = "Cambridge, ON, Canada"
WATERLOO = (WATERLOO_LABEL, 43.4643, -80.5204)
CAMBRIDGE = (CAMBRIDGE_LABEL, 43.3616, -80.3144)


def ors_route(
    points: list[tuple[float, float]],
    distance_m: float,
    duration_s: float,
    way_types: dict[int, float] | None = None,
    elevations: list[float] | None = None,
) -> dict[str, Any]:
    if elevations is None:
        elevations = [300.0 + (i % 10) for i in range(len(points))]
    route: dict[str, Any] = {
        "summary": {"distance": distance_m, "duration": duration_s},
        "geometry": encode_polyline(points, elevations),
        "way_points": [0, len(points) - 1],
    }
    if way_types is not None:
        total = sum(way_types.values())
        route["extras"] = {
            "waytype": {
                "values": [],
                "summary": [
                    {"value": code, "distance": distance, "amount": distance / total * 100}
                    for code, distance in way_types.items()
                ],
            }
        }
    return route


def ors_response(*routes: dict[str, Any]) -> dict[str, Any]:
    return {"routes": list(routes), "metadata": {"service": "routing"}}


# Two candidates between Waterloo and Cambridge.
DIRECT_ROUTE_POINTS = [(43.4643, -80.5204), (43.43, -80.45), (43.3616, -80.3144)]
SCENIC_ROUTE_POINTS = [(43.4643, -80.5204), (43.45, -80.40), (43.3616, -80.3144)]


def default_ors_response() -> dict[str, Any]:
    return ors_response(
        # Shorter but mostly on roads.
        ors_route(DIRECT_ROUTE_POINTS, 21_000, 4_500, {2: 15_000, 3: 6_000}),
        # Longer but mostly on cycleways and paths.
        ors_route(SCENIC_ROUTE_POINTS, 24_000, 5_200, {6: 16_000, 4: 6_000, 3: 2_000}),
    )


def make_metrics(
    distance_km: float,
    elevation_gain_m: float | None = 100.0,
    safety_score: float | None = 70.0,
    way_type_shares: dict[str, float] | None = None,
    repeated_share: float = 0.0,
    geometry: list[Coordinate] | None = None,
) -> RouteMetrics:
    return RouteMetrics(
        geometry=geometry or [Coordinate(43.0, -80.0), Coordinate(43.1, -80.1)],
        distance_km=distance_km,
        duration_min=distance_km / 18 * 60,
        elevation_gain_m=elevation_gain_m,
        elevation_profile=[],
        way_type_shares=way_type_shares or {},
        safety_score=safety_score,
        repeated_share=repeated_share,
    )


def photon_place(lat: float, lon: float, **properties: str) -> dict[str, Any]:
    """One Photon feature. Properties are name/housenumber/street/city/state/country."""
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": properties,
    }


def photon_response(*features: dict[str, Any]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": list(features)}


PHOTON_WATERLOO = photon_place(
    43.4643, -80.5204, name="Waterloo", state="Ontario", country="Canada"
)
PHOTON_WATERLOO_LABEL = "Waterloo, Ontario, Canada"
