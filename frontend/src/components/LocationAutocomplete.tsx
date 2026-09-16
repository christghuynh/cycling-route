import { useEffect, useId, useState, type KeyboardEvent } from "react";

import { ApiError, autocompleteLocations } from "../services/api";
import type { Location, SelectedLocation } from "../types/route";

interface LocationAutocompleteProps {
  label: string;
  placeholder: string;
  value: SelectedLocation | null;
  onChange: (location: SelectedLocation | null) => void;
  /** Bias suggestions towards this point, e.g. the start when picking a destination. */
  focus?: { lat: number; lon: number } | null;
  allowCurrentLocation?: boolean;
}

const MIN_QUERY_LENGTH = 3;
const DEBOUNCE_MS = 300;

type LookupState = "idle" | "loading" | "empty" | "error";

export function LocationAutocomplete({
  label,
  placeholder,
  value,
  onChange,
  focus = null,
  allowCurrentLocation = false,
}: LocationAutocompleteProps) {
  const inputId = useId();
  const listId = useId();
  const [text, setText] = useState(value?.label ?? "");
  const [suggestions, setSuggestions] = useState<Location[]>([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [lookup, setLookup] = useState<LookupState>("idle");
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);

  const focusLat = focus?.lat;
  const focusLon = focus?.lon;
  const query = text.trim();
  const shouldSearch = open && !value && query.length >= MIN_QUERY_LENGTH;

  useEffect(() => {
    if (!shouldSearch) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLookup("loading");
      try {
        const focusPoint =
          focusLat !== undefined && focusLon !== undefined
            ? { lat: focusLat, lon: focusLon }
            : null;
        const results = await autocompleteLocations(query, focusPoint, controller.signal);
        setSuggestions(results);
        setActiveIndex(results.length > 0 ? 0 : -1);
        setLookup(results.length > 0 ? "idle" : "empty");
      } catch (error) {
        if (controller.signal.aborted) return;
        setSuggestions([]);
        setLookup("error");
        setLookupError(error instanceof ApiError ? error.message : "Couldn't load suggestions.");
      }
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [shouldSearch, query, focusLat, focusLon]);

  function select(location: Location) {
    onChange({ label: location.display_name, lat: location.lat, lon: location.lon });
    setText(location.display_name);
    setOpen(false);
    setSuggestions([]);
  }

  function handleTextChange(newText: string) {
    setText(newText);
    setOpen(true);
    setLookup("idle");
    if (value) onChange(null);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!open || suggestions.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % suggestions.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => (index - 1 + suggestions.length) % suggestions.length);
    } else if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault();
      const suggestion = suggestions[activeIndex];
      if (suggestion) select(suggestion);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  function locateUser() {
    if (!navigator.geolocation) {
      setLookup("error");
      setLookupError("Your browser can't share its location.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocating(false);
        const location = {
          label: "My location",
          lat: position.coords.latitude,
          lon: position.coords.longitude,
        };
        onChange(location);
        setText(location.label);
        setOpen(false);
      },
      () => {
        setLocating(false);
        setLookup("error");
        setLookupError("Couldn't get your location. Check the browser's location permission.");
      },
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }

  const showList = open && !value && query.length >= MIN_QUERY_LENGTH;
  const activeId = activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined;

  return (
    <div className="field autocomplete">
      <div className="autocomplete__label-row">
        <label htmlFor={inputId}>{label}</label>
        {allowCurrentLocation && (
          <button type="button" className="link-button" onClick={locateUser} disabled={locating}>
            {locating ? "Locating…" : "Use my location"}
          </button>
        )}
      </div>
      <div className="autocomplete__input-wrap">
        <input
          id={inputId}
          type="text"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={showList ? activeId : undefined}
          placeholder={placeholder}
          value={text}
          maxLength={200}
          autoComplete="off"
          className={value ? "is-selected" : undefined}
          onChange={(event) => handleTextChange(event.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
        />
        {value && (
          <span className="autocomplete__check" aria-label="Location selected">
            ✓
          </span>
        )}
      </div>

      {showList && (
        <ul id={listId} role="listbox" className="autocomplete__list">
          {lookup === "loading" && suggestions.length === 0 && (
            <li className="autocomplete__status">Searching…</li>
          )}
          {lookup === "empty" && <li className="autocomplete__status">No matching places.</li>}
          {lookup === "error" && <li className="autocomplete__status">{lookupError}</li>}
          {suggestions.map((suggestion, index) => (
            <li
              key={`${suggestion.display_name}-${suggestion.lat}-${suggestion.lon}`}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === activeIndex}
              className={index === activeIndex ? "is-active" : undefined}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => select(suggestion)}
              onMouseEnter={() => setActiveIndex(index)}
            >
              {suggestion.display_name}
            </li>
          ))}
        </ul>
      )}
      {!showList && lookup === "error" && lookupError && (
        <p className="field-hint field-hint--error">{lookupError}</p>
      )}
    </div>
  );
}
