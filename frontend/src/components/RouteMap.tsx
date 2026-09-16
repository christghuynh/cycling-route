import "leaflet/dist/leaflet.css";

import { latLngBounds } from "leaflet";
import { useEffect, useRef } from "react";
import {
  CircleMarker,
  LayersControl,
  MapContainer,
  Polyline,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";

import type { Point } from "../hooks/useUserLocation";
import type { Location, Route } from "../types/route";
import { routeColor } from "../utils/routeColors";

interface RouteMapProps {
  routes: Route[];
  start: Location | null;
  destination: Location | null;
  selectedRouteId: string | null;
  onSelect: (routeId: string) => void;
  /** Recentre here when it appears, e.g. once the browser shares the rider's position. */
  centerOn?: Point | null;
  /** Reports the visible centre so location searches can be biased towards it. */
  onCenterChange?: (center: Point) => void;
}

const DEFAULT_CENTER: [number, number] = [43.43, -80.45];
const DEFAULT_ZOOM = 11;
const USER_LOCATION_ZOOM = 13;

function FitToRoutes({ routes }: { routes: Route[] }) {
  const map = useMap();

  useEffect(() => {
    const points = routes.flatMap((route) => route.geometry);
    if (points.length > 0) {
      map.fitBounds(latLngBounds(points), { padding: [40, 40] });
    }
  }, [map, routes]);

  return null;
}

function RecenterOn({ center }: { center: Point | null | undefined }) {
  const map = useMap();
  const applied = useRef<string | null>(null);

  useEffect(() => {
    if (!center) return;
    const key = `${center.lat},${center.lon}`;
    // Only move for a genuinely new target, so reporting the centre back cannot loop.
    if (applied.current === key) return;
    applied.current = key;
    map.setView([center.lat, center.lon], USER_LOCATION_ZOOM);
  }, [map, center]);

  return null;
}

function ReportCenter({ onCenterChange }: { onCenterChange?: (center: Point) => void }) {
  const map = useMapEvents({
    moveend: () => {
      const { lat, lng } = map.getCenter();
      onCenterChange?.({ lat, lon: lng });
    },
  });
  return null;
}

function RouteLine({
  route,
  selected,
  onSelect,
}: {
  route: Route;
  selected: boolean;
  onSelect: (routeId: string) => void;
}) {
  const color = routeColor(route.rank);
  const eventHandlers = { click: () => onSelect(route.id) };

  return (
    <>
      {selected && (
        <Polyline
          positions={route.geometry}
          pathOptions={{ color: "#ffffff", weight: 10, opacity: 0.9 }}
          interactive={false}
        />
      )}
      <Polyline
        positions={route.geometry}
        pathOptions={{
          color,
          weight: selected ? 6 : 4,
          opacity: selected ? 1 : 0.5,
        }}
        eventHandlers={eventHandlers}
      >
        <Tooltip sticky>
          Route #{route.rank} · {Math.round(route.overall_score)}/100
        </Tooltip>
      </Polyline>
    </>
  );
}

export function RouteMap({
  routes,
  start,
  destination,
  selectedRouteId,
  onSelect,
  centerOn,
  onCenterChange,
}: RouteMapProps) {
  const selected = routes.find((route) => route.id === selectedRouteId);
  const others = routes.filter((route) => route.id !== selectedRouteId);

  return (
    <MapContainer center={DEFAULT_CENTER} zoom={DEFAULT_ZOOM} className="map" scrollWheelZoom>
      <LayersControl position="topright">
        <LayersControl.BaseLayer checked name="Cycling (bike lanes & trails)">
          <TileLayer
            attribution='<a href="https://www.cyclosm.org">CyclOSM</a> | &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png"
            maxZoom={20}
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name="Streets">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
        </LayersControl.BaseLayer>
      </LayersControl>
      <FitToRoutes routes={routes} />
      <RecenterOn center={centerOn} />
      <ReportCenter onCenterChange={onCenterChange} />

      {/* Unselected routes first so the selected route is drawn on top. */}
      {others.map((route) => (
        <RouteLine key={route.id} route={route} selected={false} onSelect={onSelect} />
      ))}
      {selected && (
        <RouteLine key={`selected-${selected.id}`} route={selected} selected onSelect={onSelect} />
      )}

      {start && (
        <CircleMarker
          center={[start.lat, start.lon]}
          radius={8}
          pathOptions={{ color: "#ffffff", weight: 3, fillColor: "#15803d", fillOpacity: 1 }}
        >
          <Tooltip>
            {destination ? "Start" : "Start & finish"}: {start.display_name}
          </Tooltip>
        </CircleMarker>
      )}
      {destination && (
        <CircleMarker
          center={[destination.lat, destination.lon]}
          radius={8}
          pathOptions={{ color: "#ffffff", weight: 3, fillColor: "#b91c1c", fillOpacity: 1 }}
        >
          <Tooltip>Finish: {destination.display_name}</Tooltip>
        </CircleMarker>
      )}
    </MapContainer>
  );
}
