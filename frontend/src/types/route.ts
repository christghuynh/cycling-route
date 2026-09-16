/** Types mirroring the backend API schemas (backend/app/schemas/route.py). */

export type TripMode = "loop" | "distance_goal" | "point_to_point";
export type BikeType = "road" | "hybrid" | "mountain";

export interface Preferences {
  distance_weight: number;
  elevation_weight: number;
  safety_weight: number;
}

/** A place the user picked: from autocomplete, or their current position. */
export interface SelectedLocation {
  label: string;
  lat: number;
  lon: number;
}

export interface RouteRequest {
  mode: TripMode;
  start: SelectedLocation;
  destination: SelectedLocation | null;
  target_distance_km: number | null;
  bike_type: BikeType;
  preferences: Preferences;
}

export interface Location {
  query: string;
  display_name: string;
  lat: number;
  lon: number;
}

export type LatLon = [number, number];

export interface Route {
  id: string;
  rank: number;
  distance_km: number;
  elevation_gain_m: number | null;
  duration_min: number;
  /** Estimated proxy derived from way types; not an authoritative safety rating. */
  safety_score: number | null;
  distance_score: number;
  elevation_score: number | null;
  overall_score: number;
  /** Share of the ride (0-1) that doubles back over road already ridden. */
  repeated_share: number;
  summary: string;
  highlights: string[];
  way_type_shares: Record<string, number>;
  geometry: LatLon[];
  /** [distance_km, elevation_m] pairs. */
  elevation_profile: [number, number][];
}

export interface RouteSearchResult {
  search_id: string;
  created_at: string;
  mode: TripMode;
  bike_type: BikeType;
  target_distance_km: number | null;
  start: Location;
  destination: Location | null;
  preferences: Preferences;
  warnings: string[];
  routes: Route[];
}

export interface AutocompleteResult {
  suggestions: Location[];
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: { field: string; message: string }[];
  };
}
