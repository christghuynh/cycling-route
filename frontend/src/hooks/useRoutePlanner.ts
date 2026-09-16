import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, generateRoutes } from "../services/api";
import type { RouteRequest, RouteSearchResult } from "../types/route";

export type PlannerStatus = "idle" | "loading" | "success" | "error";

interface PlannerState {
  status: PlannerStatus;
  result: RouteSearchResult | null;
  error: string | null;
  selectedRouteId: string | null;
}

const INITIAL_STATE: PlannerState = {
  status: "idle",
  result: null,
  error: null,
  selectedRouteId: null,
};

export function useRoutePlanner() {
  const [state, setState] = useState<PlannerState>(INITIAL_STATE);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const search = useCallback(async (request: RouteRequest) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    // Keep previous results visible while loading so the map does not flash empty.
    setState((previous) => ({ ...previous, status: "loading", error: null }));
    try {
      const result = await generateRoutes(request, controller.signal);
      setState({
        status: "success",
        result,
        error: null,
        selectedRouteId: result.routes[0]?.id ?? null,
      });
    } catch (error) {
      if (controller.signal.aborted) return;
      const message =
        error instanceof ApiError ? error.message : "Something went wrong. Please try again.";
      setState((previous) => ({ ...previous, status: "error", error: message }));
    }
  }, []);

  const selectRoute = useCallback((routeId: string) => {
    setState((previous) => ({ ...previous, selectedRouteId: routeId }));
  }, []);

  const selectedRoute =
    state.result?.routes.find((route) => route.id === state.selectedRouteId) ?? null;

  return { ...state, selectedRoute, search, selectRoute };
}
