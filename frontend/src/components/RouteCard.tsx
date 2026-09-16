import type { Route } from "../types/route";
import { formatDistance, formatDuration, formatElevation, formatScore } from "../utils/format";
import { routeColor } from "../utils/routeColors";

interface RouteCardProps {
  route: Route;
  targetDistanceKm: number | null;
  selected: boolean;
  onSelect: (routeId: string) => void;
}

export function RouteCard({ route, targetDistanceKm, selected, onSelect }: RouteCardProps) {
  const recommended = route.rank === 1;

  return (
    <button
      type="button"
      className={`route-card${selected ? " route-card--selected" : ""}`}
      style={{ borderLeftColor: routeColor(route.rank) }}
      onClick={() => onSelect(route.id)}
      aria-pressed={selected}
    >
      <div className="route-card__header">
        <span className="route-card__rank">
          #{route.rank}
          {recommended && <span className="badge">Recommended</span>}
        </span>
        <span className="route-card__score" aria-label={`Overall score ${route.overall_score}`}>
          {Math.round(route.overall_score)}
          <small>/100</small>
        </span>
      </div>

      <dl className="route-card__stats">
        <div>
          <dt>Distance</dt>
          <dd>
            {formatDistance(route.distance_km)}
            {targetDistanceKm !== null && (
              <span className="route-card__target"> of {targetDistanceKm}</span>
            )}
          </dd>
        </div>
        <div>
          <dt>Climbing</dt>
          <dd>{formatElevation(route.elevation_gain_m)}</dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd>{formatDuration(route.duration_min)}</dd>
        </div>
        <div>
          <dt>Est. safety</dt>
          <dd>{formatScore(route.safety_score)}</dd>
        </div>
      </dl>

      <p className="route-card__summary">{route.summary}</p>
    </button>
  );
}
