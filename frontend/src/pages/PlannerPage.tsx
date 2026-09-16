import { RouteDetails } from "../components/RouteDetails";
import { RouteList } from "../components/RouteList";
import { RouteMap } from "../components/RouteMap";
import { SearchForm } from "../components/SearchForm";
import { StatusMessage } from "../components/StatusMessage";
import { useState } from "react";

import { useRoutePlanner } from "../hooks/useRoutePlanner";
import { useUserLocation } from "../hooks/useUserLocation";
import type { Point } from "../hooks/useUserLocation";

const DEFAULT_FOCUS: Point = { lat: 43.43, lon: -80.45 };

export function PlannerPage() {
  const { status, result, error, selectedRouteId, selectedRoute, search, selectRoute } =
    useRoutePlanner();
  const userLocation = useUserLocation();
  // Location searches are ranked around whatever part of the map is on screen.
  const [mapCenter, setMapCenter] = useState<Point>(DEFAULT_FOCUS);
  const loading = status === "loading";
  const routes = result?.routes ?? [];
  const targetDistanceKm = result?.target_distance_km ?? null;

  return (
    <div className="layout">
      <aside className="sidebar">
        <header className="app-header">
          <h1>
            <span aria-hidden="true">🚲</span> Cycling Route Planner
          </h1>
          <p>Plan training loops and rides of the distance you want.</p>
        </header>

        <SearchForm loading={loading} onSubmit={search} focusPoint={mapCenter} />

        {error && (
          <StatusMessage tone="error" title="Couldn't generate routes">
            {error}
          </StatusMessage>
        )}
        {result?.warnings.map((warning) => (
          <StatusMessage key={warning} tone="warning">
            {warning}
          </StatusMessage>
        ))}

        {routes.length > 0 && (
          <RouteList
            routes={routes}
            targetDistanceKm={targetDistanceKm}
            selectedRouteId={selectedRouteId}
            onSelect={selectRoute}
          />
        )}
        {status === "idle" && (
          <p className="muted empty-hint">
            Pick where you want to start and how far you want to ride.
          </p>
        )}
      </aside>

      <main className="main">
        <div className="map-wrapper" aria-busy={loading}>
          <RouteMap
            routes={routes}
            start={result?.start ?? null}
            destination={result?.destination ?? null}
            selectedRouteId={selectedRouteId}
            onSelect={selectRoute}
            centerOn={userLocation}
            onCenterChange={setMapCenter}
          />
          {loading && (
            <div className="map-overlay" role="status">
              <div className="spinner" aria-hidden="true" />
              <span>Building rides on real roads and trails…</span>
            </div>
          )}
        </div>

        {selectedRoute && result && (
          <RouteDetails
            route={selectedRoute}
            preferences={result.preferences}
            targetDistanceKm={targetDistanceKm}
          />
        )}
      </main>
    </div>
  );
}
