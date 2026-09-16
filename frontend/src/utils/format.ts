export function formatDistance(km: number): string {
  return `${km.toFixed(1)} km`;
}

export function formatDuration(minutes: number): string {
  const rounded = Math.round(minutes);
  if (rounded < 60) return `${rounded} min`;
  const hours = Math.floor(rounded / 60);
  const rest = rounded % 60;
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`;
}

export function formatElevation(meters: number | null): string {
  return meters === null ? "n/a" : `${Math.round(meters)} m`;
}

export function formatScore(score: number | null): string {
  return score === null ? "n/a" : `${Math.round(score)}/100`;
}

export function formatPercent(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}

const WAY_TYPE_LABELS: Record<string, string> = {
  cycleway: "Cycleway",
  path: "Path",
  street: "Residential street",
  track: "Track",
  footway: "Footway",
  ferry: "Ferry",
  road: "Road",
  state_road: "Major road",
  steps: "Steps",
  construction: "Construction",
  unknown: "Unknown",
};

export function wayTypeLabel(wayType: string): string {
  return WAY_TYPE_LABELS[wayType] ?? wayType.replace(/_/g, " ");
}

/**
 * Convert slider values (0-100 each) into the share each factor contributes to the overall score.
 * Returns zero shares when every slider is at zero.
 */
export function weightShares(values: number[]): number[] {
  const total = values.reduce((sum, value) => sum + value, 0);
  return values.map((value) => (total > 0 ? value / total : 0));
}
