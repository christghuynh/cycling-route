import type {
  ApiErrorBody,
  AutocompleteResult,
  Location,
  RouteRequest,
  RouteSearchResult,
} from "../types/route";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(message: string, code: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    typeof (value as ApiErrorBody).error?.message === "string"
  );
}

async function requestJson<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(
      "Could not reach the route planner server. Check your connection and try again.",
      "network_error",
      0,
    );
  }

  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (isApiErrorBody(body)) {
      throw new ApiError(body.error.message, body.error.code, response.status);
    }
    throw new ApiError(
      `The server returned an unexpected error (${response.status}).`,
      "unexpected_response",
      response.status,
    );
  }
  if (body === null) {
    throw new ApiError("The server returned an invalid response.", "unexpected_response", 0);
  }
  return body as T;
}

// Geocoding quota is small (about 100 calls a day on a free key) and typing repeats queries -
// backspacing, retyping, reopening a field - so successful suggestions are remembered.
const SUGGESTION_CACHE_LIMIT = 100;
const suggestionCache = new Map<string, Location[]>();

function suggestionKey(query: string, focus: { lat: number; lon: number } | null): string {
  const normalized = query.trim().toLowerCase().replace(/\s+/g, " ");
  // Focus only nudges ranking, so nearby map positions (~10 km) share cached results.
  const area = focus ? `${focus.lat.toFixed(1)},${focus.lon.toFixed(1)}` : "anywhere";
  return `${normalized}|${area}`;
}

export function clearSuggestionCache(): void {
  suggestionCache.clear();
}

export async function autocompleteLocations(
  query: string,
  focus: { lat: number; lon: number } | null,
  signal?: AbortSignal,
): Promise<Location[]> {
  const key = suggestionKey(query, focus);
  const cached = suggestionCache.get(key);
  if (cached) return cached;

  const params = new URLSearchParams({ q: query });
  if (focus) {
    params.set("focus_lat", focus.lat.toFixed(5));
    params.set("focus_lon", focus.lon.toFixed(5));
  }
  const result = await requestJson<AutocompleteResult>(`/api/locations/autocomplete?${params}`, {
    method: "GET",
    signal,
  });

  if (suggestionCache.size >= SUGGESTION_CACHE_LIMIT) {
    const oldest = suggestionCache.keys().next().value;
    if (oldest !== undefined) suggestionCache.delete(oldest);
  }
  suggestionCache.set(key, result.suggestions);
  return result.suggestions;
}

export function generateRoutes(
  request: RouteRequest,
  signal?: AbortSignal,
): Promise<RouteSearchResult> {
  return requestJson<RouteSearchResult>("/api/routes", {
    method: "POST",
    body: JSON.stringify(request),
    signal,
  });
}
