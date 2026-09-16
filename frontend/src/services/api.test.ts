import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { autocompleteLocations, clearSuggestionCache } from "./api";

const WATERLOO = {
  query: "waterloo",
  display_name: "Waterloo, ON, Canada",
  lat: 43.48,
  lon: -80.54,
};

function mockFetch() {
  const fetchMock = vi.fn(
    async () =>
      new Response(JSON.stringify({ suggestions: [WATERLOO] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("autocompleteLocations cache", () => {
  beforeEach(() => clearSuggestionCache());
  afterEach(() => vi.unstubAllGlobals());

  it("does not spend a second request on a repeated query", async () => {
    const fetchMock = mockFetch();
    const focus = { lat: 43.4643, lon: -80.5204 };

    await autocompleteLocations("waterloo", focus);
    const second = await autocompleteLocations("  Waterloo ", focus);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(second).toEqual([WATERLOO]);
  });

  it("reuses results for a slightly panned map", async () => {
    const fetchMock = mockFetch();

    await autocompleteLocations("waterloo", { lat: 43.4643, lon: -80.5204 });
    await autocompleteLocations("waterloo", { lat: 43.4701, lon: -80.5311 });

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("asks again when the map is somewhere else entirely", async () => {
    const fetchMock = mockFetch();

    await autocompleteLocations("main street", { lat: 43.65, lon: -79.38 }); // Toronto
    await autocompleteLocations("main street", { lat: 49.28, lon: -123.12 }); // Vancouver

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not cache failures", async () => {
    const failing = vi.fn(
      async () =>
        new Response(
          JSON.stringify({ error: { code: "quota_exceeded", message: "Quota used up" } }),
          {
            status: 503,
            headers: { "Content-Type": "application/json" },
          },
        ),
    );
    vi.stubGlobal("fetch", failing);
    await expect(autocompleteLocations("waterloo", null)).rejects.toThrow("Quota used up");

    const fetchMock = mockFetch();
    await expect(autocompleteLocations("waterloo", null)).resolves.toEqual([WATERLOO]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
