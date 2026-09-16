import { useState, type FormEvent } from "react";

import type { Point } from "../hooks/useUserLocation";
import type { BikeType, RouteRequest, SelectedLocation, TripMode } from "../types/route";
import { weightShares } from "../utils/format";
import { LocationAutocomplete } from "./LocationAutocomplete";
import { PreferenceSlider } from "./PreferenceSlider";

interface SearchFormProps {
  loading: boolean;
  onSubmit: (request: RouteRequest) => void;
  /** Where the map is looking; location searches are ranked around it. */
  focusPoint: Point;
}

const TRIP_MODES: { value: TripMode; label: string; hint: string }[] = [
  { value: "loop", label: "Loop", hint: "Start and finish at the same place." },
  {
    value: "distance_goal",
    label: "Ride to",
    hint: "Ride a set distance and finish somewhere else, e.g. a café.",
  },
  { value: "point_to_point", label: "A → B", hint: "Get from one place to another." },
];

const BIKE_TYPES: { value: BikeType; label: string }[] = [
  { value: "road", label: "Road bike" },
  { value: "hybrid", label: "Hybrid / city" },
  { value: "mountain", label: "Mountain / gravel" },
];

const DISTANCE_PRESETS_KM = [20, 30, 50, 80];
const MIN_DISTANCE_KM = 2;
const MAX_DISTANCE_KM = 150;

type PreferenceKey = "distance" | "elevation" | "safety";

export function SearchForm({ loading, onSubmit, focusPoint }: SearchFormProps) {
  const [mode, setMode] = useState<TripMode>("loop");
  const [start, setStart] = useState<SelectedLocation | null>(null);
  const [destination, setDestination] = useState<SelectedLocation | null>(null);
  const [distanceKm, setDistanceKm] = useState("30");
  const [bikeType, setBikeType] = useState<BikeType>("road");
  const [weights, setWeights] = useState<Record<PreferenceKey, number>>({
    distance: 50,
    elevation: 20,
    safety: 30,
  });
  const [validationError, setValidationError] = useState<string | null>(null);

  const hasTarget = mode !== "point_to_point";
  const preferences = [
    {
      key: "distance" as const,
      label: hasTarget ? "Match my distance" : "Short distance",
      hint: hasTarget ? "Prefer rides closest to your target." : "Prefer routes with less detour.",
    },
    { key: "elevation" as const, label: "Less climbing", hint: "Prefer flatter routes." },
    {
      key: "safety" as const,
      label: "Estimated safety",
      hint: "Prefer bike paths and quiet streets.",
    },
  ];
  const shares = weightShares(preferences.map(({ key }) => weights[key]));

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const target = Number(distanceKm);

    if (!start) {
      setValidationError("Choose a start from the suggestions, or use your location.");
      return;
    }
    if (mode !== "loop" && !destination) {
      setValidationError("Choose a destination from the suggestions.");
      return;
    }
    if (hasTarget && !(target >= MIN_DISTANCE_KM && target <= MAX_DISTANCE_KM)) {
      setValidationError(`Enter a distance between ${MIN_DISTANCE_KM} and ${MAX_DISTANCE_KM} km.`);
      return;
    }
    if (shares.every((share) => share === 0)) {
      setValidationError("Give at least one preference a weight above zero.");
      return;
    }

    setValidationError(null);
    onSubmit({
      mode,
      start,
      destination: mode === "loop" ? null : destination,
      target_distance_km: hasTarget ? target : null,
      bike_type: bikeType,
      preferences: {
        distance_weight: weights.distance / 100,
        elevation_weight: weights.elevation / 100,
        safety_weight: weights.safety / 100,
      },
    });
  }

  const activeMode = TRIP_MODES.find((option) => option.value === mode);

  return (
    <form className="search-form" onSubmit={handleSubmit} noValidate>
      <fieldset className="segmented" aria-describedby="trip-mode-hint">
        <legend>Trip type</legend>
        <div className="segmented__options">
          {TRIP_MODES.map((option) => (
            <label key={option.value} className={mode === option.value ? "is-checked" : undefined}>
              <input
                type="radio"
                name="trip-mode"
                value={option.value}
                checked={mode === option.value}
                onChange={() => setMode(option.value)}
              />
              {option.label}
            </label>
          ))}
        </div>
        <p id="trip-mode-hint" className="field-hint">
          {activeMode?.hint}
        </p>
      </fieldset>

      <LocationAutocomplete
        label={mode === "loop" ? "Start & finish" : "Start"}
        placeholder="Search for an address or place"
        value={start}
        onChange={setStart}
        focus={focusPoint}
        allowCurrentLocation
      />

      {mode !== "loop" && (
        <LocationAutocomplete
          label={mode === "distance_goal" ? "Finish" : "Destination"}
          placeholder="Search for an address or place"
          value={destination}
          onChange={setDestination}
          focus={start ?? focusPoint}
        />
      )}

      {hasTarget && (
        <div className="field">
          <label htmlFor="distance">Ride distance</label>
          <div className="distance-input">
            <input
              id="distance"
              type="number"
              inputMode="decimal"
              min={MIN_DISTANCE_KM}
              max={MAX_DISTANCE_KM}
              step={1}
              value={distanceKm}
              onChange={(event) => setDistanceKm(event.target.value)}
            />
            <span>km</span>
            <div className="chips">
              {DISTANCE_PRESETS_KM.map((preset) => (
                <button
                  key={preset}
                  type="button"
                  className={Number(distanceKm) === preset ? "chip is-active" : "chip"}
                  onClick={() => setDistanceKm(String(preset))}
                >
                  {preset}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="field">
        <label htmlFor="bike-type">Bike</label>
        <select
          id="bike-type"
          value={bikeType}
          onChange={(event) => setBikeType(event.target.value as BikeType)}
        >
          {BIKE_TYPES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <details className="preferences">
        <summary>Ranking preferences</summary>
        {preferences.map(({ key, label, hint }, index) => (
          <PreferenceSlider
            key={key}
            id={`weight-${key}`}
            label={label}
            hint={hint}
            value={weights[key]}
            share={shares[index] ?? 0}
            onChange={(value) => setWeights((previous) => ({ ...previous, [key]: value }))}
          />
        ))}
      </details>

      {validationError && (
        <p className="form-error" role="alert">
          {validationError}
        </p>
      )}

      <button type="submit" className="button-primary" disabled={loading}>
        {loading ? "Finding routes…" : hasTarget ? "Find rides" : "Find routes"}
      </button>
    </form>
  );
}
