import { describe, expect, it } from "vitest";

import {
  formatDistance,
  formatDuration,
  formatElevation,
  formatScore,
  wayTypeLabel,
  weightShares,
} from "./format";

describe("formatDuration", () => {
  it.each([
    [42.4, "42 min"],
    [60, "1 h"],
    [82, "1 h 22 min"],
    [179.6, "3 h"],
  ])("formats %d minutes as %s", (minutes, expected) => {
    expect(formatDuration(minutes)).toBe(expected);
  });
});

describe("formatDistance", () => {
  it("shows one decimal place", () => {
    expect(formatDistance(3.456)).toBe("3.5 km");
    expect(formatDistance(31.44)).toBe("31.4 km");
  });
});

describe("nullable metrics", () => {
  it("shows n/a when data is unavailable", () => {
    expect(formatElevation(null)).toBe("n/a");
    expect(formatScore(null)).toBe("n/a");
    expect(formatScore(83.6)).toBe("84/100");
  });
});

describe("wayTypeLabel", () => {
  it("uses friendly labels and falls back to the raw name", () => {
    expect(wayTypeLabel("state_road")).toBe("Major road");
    expect(wayTypeLabel("bridle_way")).toBe("bridle way");
  });
});

describe("weightShares", () => {
  it("normalises slider values to shares", () => {
    expect(weightShares([40, 30, 30])).toEqual([0.4, 0.3, 0.3]);
    expect(weightShares([50, 50, 0])).toEqual([0.5, 0.5, 0]);
  });

  it("returns zero shares when all sliders are zero", () => {
    expect(weightShares([0, 0, 0])).toEqual([0, 0, 0]);
  });
});
