import type { Preferences, Route } from "../types/route";
import { routeColor } from "../utils/routeColors";
import { ElevationProfile } from "./ElevationProfile";
import { ScoreBreakdown } from "./ScoreBreakdown";
import { WayTypeBreakdown } from "./WayTypeBreakdown";

interface RouteDetailsProps {
  route: Route;
  preferences: Preferences;
  targetDistanceKm: number | null;
}

export function RouteDetails({ route, preferences, targetDistanceKm }: RouteDetailsProps) {
  const color = routeColor(route.rank);

  return (
    <section className="route-details" aria-labelledby="details-heading">
      <header className="route-details__header">
        <span className="swatch swatch--large" style={{ background: color }} />
        <div>
          <h2 id="details-heading">Why route #{route.rank}?</h2>
          <p>{route.summary}</p>
        </div>
      </header>

      <div className="route-details__grid">
        <div>
          <h3>Score breakdown</h3>
          <ScoreBreakdown
            route={route}
            preferences={preferences}
            targetDistanceKm={targetDistanceKm}
          />
          {route.highlights.length > 0 && (
            <ul className="highlights">
              {route.highlights.map((highlight) => (
                <li key={highlight}>{highlight}</li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <h3>Elevation profile</h3>
          <ElevationProfile profile={route.elevation_profile} color={color} />

          <h3>Way types</h3>
          <WayTypeBreakdown shares={route.way_type_shares} />
          <p className="disclaimer">
            The safety score is an <strong>estimate</strong> based on the kinds of ways the route
            uses (from OpenStreetMap data). It does not account for traffic volume, speed limits, or
            collision history.
          </p>
        </div>
      </div>
    </section>
  );
}
