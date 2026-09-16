import { useEffect, useState } from "react";

export interface Point {
  lat: number;
  lon: number;
}

/**
 * Asks the browser for the rider's position once on load, to centre the map and bias location
 * searches towards where they are. Denial is expected and harmless: the app falls back to the
 * default map view.
 */
export function useUserLocation() {
  const [location, setLocation] = useState<Point | null>(null);

  useEffect(() => {
    if (!navigator.geolocation) return;
    let cancelled = false;
    navigator.geolocation.getCurrentPosition(
      (position) => {
        if (!cancelled) {
          setLocation({ lat: position.coords.latitude, lon: position.coords.longitude });
        }
      },
      () => {
        /* Denied or unavailable: keep the default view. */
      },
      { timeout: 10_000, maximumAge: 300_000 },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  return location;
}
