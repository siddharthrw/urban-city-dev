import { describe, expect, it } from "vitest";
import { formatBytes, formatLength, formatValue, linkMethodLabel, nameMatchLabel } from "./format";

describe("formatValue", () => {
  it("shows a dash for empty values", () => {
    expect(formatValue(null)).toBe("—");
    expect(formatValue(undefined)).toBe("—");
    expect(formatValue("")).toBe("—");
  });
  it("formats numbers with Indian grouping, integers without decimals", () => {
    expect(formatValue(1250)).toBe("1,250");
    expect(formatValue(24.567)).toBe("24.57");
  });
  it("formats booleans as Yes/No", () => {
    expect(formatValue(true)).toBe("Yes");
    expect(formatValue(false)).toBe("No");
  });
  it("joins arrays", () => {
    expect(formatValue(["a", "b"])).toBe("a, b");
  });
  it("stringifies anything else", () => {
    expect(formatValue("hello")).toBe("hello");
  });
});

describe("formatLength", () => {
  it("uses km above 1000 m", () => {
    expect(formatLength(1500)).toBe("1.50 km");
    expect(formatLength(999)).toBe("999 m");
    expect(formatLength(1000)).toBe("1.00 km");
  });
});

describe("formatBytes", () => {
  it("scales to MB/KB/B", () => {
    expect(formatBytes(2_500_000)).toBe("2.5 MB");
    expect(formatBytes(1500)).toBe("2 KB");
    expect(formatBytes(500)).toBe("500 B");
  });
});

describe("labels", () => {
  it("has a label for every link method used by the backend", () => {
    for (const m of ["location", "name", "name_fuzzy", "manual"]) {
      expect(linkMethodLabel(m)).not.toBe("");
    }
  });
  it("falls back to the raw string for an unknown method", () => {
    expect(linkMethodLabel("mystery")).toBe("");
  });
  it("has a label for every name_match value the backend returns", () => {
    for (const m of ["same", "similar", "different", "osm_only", "official_only", "none"]) {
      expect(nameMatchLabel(m)).toBeTruthy();
    }
  });
});
