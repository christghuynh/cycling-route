/** Map/card colour for each rank. Rank 1 uses the brand green so the recommendation stands out. */
const RANK_COLORS = ["#15803d", "#2563eb", "#9333ea", "#c2410c"];

export function routeColor(rank: number): string {
  return RANK_COLORS[(rank - 1) % RANK_COLORS.length] ?? "#475569";
}
