import type { Route } from "../types/route";
import { RouteCard } from "./RouteCard";

interface RouteListProps {
  routes: Route[];
  targetDistanceKm: number | null;
  selectedRouteId: string | null;
  onSelect: (routeId: string) => void;
}

export function RouteList({ routes, targetDistanceKm, selectedRouteId, onSelect }: RouteListProps) {
  return (
    <section aria-labelledby="routes-heading" className="route-list">
      <h2 id="routes-heading">
        {routes.length} {targetDistanceKm !== null ? "ride" : "route"}
        {routes.length === 1 ? "" : "s"} found
      </h2>
      <ol>
        {routes.map((route) => (
          <li key={route.id}>
            <RouteCard
              route={route}
              targetDistanceKm={targetDistanceKm}
              selected={route.id === selectedRouteId}
              onSelect={onSelect}
            />
          </li>
        ))}
      </ol>
    </section>
  );
}
