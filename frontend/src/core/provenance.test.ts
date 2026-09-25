import { describe, expect, it } from "vitest";
import { CONFIDENCE } from "./provenance";

describe("CONFIDENCE", () => {
  it("defines all three width sources the backend can return", () => {
    expect(Object.keys(CONFIDENCE).sort()).toEqual(["estimated", "measured", "verified"]);
  });
  it("gives each a distinct color, label and help text", () => {
    const colors = new Set(Object.values(CONFIDENCE).map((c) => c.color));
    expect(colors.size).toBe(3);
    for (const c of Object.values(CONFIDENCE)) {
      expect(c.label).toBeTruthy();
      expect(c.help).toBeTruthy();
      expect(c.badge).toBeTruthy();
    }
  });
});
