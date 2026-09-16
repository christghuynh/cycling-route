interface ElevationProfileProps {
  profile: [number, number][];
  color: string;
}

const WIDTH = 600;
const HEIGHT = 140;
const PADDING = { top: 10, right: 10, bottom: 22, left: 40 };

export function ElevationProfile({ profile, color }: ElevationProfileProps) {
  if (profile.length < 2) {
    return <p className="muted">Elevation profile unavailable.</p>;
  }

  const distances = profile.map(([distance]) => distance);
  const elevations = profile.map(([, elevation]) => elevation);
  const maxDistance = Math.max(...distances) || 1;
  const minElevation = Math.min(...elevations);
  const maxElevation = Math.max(...elevations);
  // Pad the vertical range so gentle terrain does not look like mountains.
  const range = Math.max(maxElevation - minElevation, 30);
  const floor = minElevation - (range - (maxElevation - minElevation)) / 2;

  const plotWidth = WIDTH - PADDING.left - PADDING.right;
  const plotHeight = HEIGHT - PADDING.top - PADDING.bottom;
  const x = (distance: number) => PADDING.left + (distance / maxDistance) * plotWidth;
  const y = (elevation: number) =>
    PADDING.top + plotHeight - ((elevation - floor) / range) * plotHeight;

  const line = profile.map(([d, e], i) => `${i === 0 ? "M" : "L"}${x(d)},${y(e)}`).join(" ");
  const baseline = PADDING.top + plotHeight;
  const area = `${line} L${x(maxDistance)},${baseline} L${x(0)},${baseline} Z`;

  return (
    <svg
      className="elevation-profile"
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      role="img"
      aria-label={`Elevation profile from ${Math.round(minElevation)} m to ${Math.round(maxElevation)} m`}
    >
      <path d={area} fill={color} opacity={0.15} />
      <path d={line} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
      <g className="elevation-profile__axis">
        <text x={PADDING.left - 6} y={y(maxElevation) + 4} textAnchor="end">
          {Math.round(maxElevation)} m
        </text>
        <text x={PADDING.left - 6} y={y(minElevation) + 4} textAnchor="end">
          {Math.round(minElevation)} m
        </text>
        <text x={x(0)} y={HEIGHT - 6}>
          0 km
        </text>
        <text x={x(maxDistance)} y={HEIGHT - 6} textAnchor="end">
          {maxDistance.toFixed(1)} km
        </text>
      </g>
    </svg>
  );
}
