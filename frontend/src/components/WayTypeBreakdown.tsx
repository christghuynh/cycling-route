import { formatPercent, wayTypeLabel } from "../utils/format";

const WAY_TYPE_COLORS: Record<string, string> = {
  cycleway: "#15803d",
  path: "#4ade80",
  street: "#a3e635",
  track: "#facc15",
  footway: "#94a3b8",
  ferry: "#38bdf8",
  road: "#fb923c",
  state_road: "#dc2626",
  steps: "#7c3aed",
  construction: "#78350f",
  unknown: "#cbd5e1",
};

export function WayTypeBreakdown({ shares }: { shares: Record<string, number> }) {
  const entries = Object.entries(shares).sort(([, a], [, b]) => b - a);
  if (entries.length === 0) {
    return <p className="muted">Way type information unavailable.</p>;
  }

  return (
    <div className="way-types">
      <div className="way-types__bar" role="img" aria-label="Share of route by way type">
        {entries.map(([wayType, share]) => (
          <span
            key={wayType}
            style={{ width: `${share * 100}%`, background: WAY_TYPE_COLORS[wayType] ?? "#cbd5e1" }}
            title={`${wayTypeLabel(wayType)}: ${formatPercent(share)}`}
          />
        ))}
      </div>
      <ul className="way-types__legend">
        {entries.map(([wayType, share]) => (
          <li key={wayType}>
            <span
              className="swatch"
              style={{ background: WAY_TYPE_COLORS[wayType] ?? "#cbd5e1" }}
            />
            {wayTypeLabel(wayType)} <span className="muted">{formatPercent(share)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
