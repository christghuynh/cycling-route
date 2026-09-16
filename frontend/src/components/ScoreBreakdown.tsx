import type { Preferences, Route } from "../types/route";
import { formatPercent } from "../utils/format";

interface ScoreBreakdownProps {
  route: Route;
  preferences: Preferences;
  targetDistanceKm: number | null;
}

interface Component {
  label: string;
  score: number | null;
  weight: number;
  explanation: string;
}

/**
 * Shows how each component contributed to the overall score. Mirrors the backend formula:
 * a weighted average over the components that were available for this search.
 */
export function ScoreBreakdown({ route, preferences, targetDistanceKm }: ScoreBreakdownProps) {
  const components: Component[] = [
    {
      label: targetDistanceKm !== null ? "Target distance" : "Distance",
      score: route.distance_score,
      weight: preferences.distance_weight,
      explanation:
        targetDistanceKm !== null
          ? `100 at exactly ${targetDistanceKm} km; 0 at 30% over or under.`
          : "100 for the shortest option; 0 at 50% longer.",
    },
    {
      label: "Elevation",
      score: route.elevation_score,
      weight: preferences.elevation_weight,
      explanation: "100 for flat; 0 at 25 m of climbing per km.",
    },
    {
      label: "Estimated safety",
      score: route.safety_score,
      weight: preferences.safety_weight,
      explanation: "Based on the share of cycleways, paths, and quiet streets.",
    },
  ];

  const used = components.filter((component) => component.score !== null);
  const usedWeight = used.reduce((sum, component) => sum + component.weight, 0);
  // Backend falls back to equal weights if every available factor has zero weight.
  const weightOf = (component: Component) =>
    usedWeight === 0 ? 1 / used.length : component.weight / usedWeight;

  return (
    <table className="score-table">
      <thead>
        <tr>
          <th scope="col">Factor</th>
          <th scope="col">Score</th>
          <th scope="col">Weight</th>
          <th scope="col">Points</th>
        </tr>
      </thead>
      <tbody>
        {components.map((component) => {
          const effectiveWeight = component.score === null ? 0 : weightOf(component);
          return (
            <tr key={component.label}>
              <th scope="row">
                {component.label}
                <span className="score-table__hint">{component.explanation}</span>
              </th>
              <td>
                {component.score === null ? (
                  <span className="muted">not used</span>
                ) : (
                  <div className="score-bar">
                    <div
                      className="score-bar__fill"
                      style={{ width: `${Math.max(0, Math.min(100, component.score))}%` }}
                    />
                    <span>{Math.round(component.score)}</span>
                  </div>
                )}
              </td>
              <td>{formatPercent(effectiveWeight)}</td>
              <td>
                {component.score === null ? "–" : (component.score * effectiveWeight).toFixed(1)}
              </td>
            </tr>
          );
        })}
      </tbody>
      <tfoot>
        <tr>
          <th scope="row">Overall</th>
          <td colSpan={2} />
          <td>
            <strong>{route.overall_score.toFixed(1)}</strong>
          </td>
        </tr>
      </tfoot>
    </table>
  );
}
