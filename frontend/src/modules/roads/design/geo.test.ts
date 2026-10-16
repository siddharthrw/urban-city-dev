import { describe, expect, it } from "vitest";
import { projectLocal } from "./geo";

describe("projectLocal", () => {
  it("places the centroid at the origin", () => {
    const pts = projectLocal([[80.2, 13.0], [80.21, 13.01]]);
    const avgX = pts.reduce((s, p) => s + p.x, 0) / pts.length;
    const avgY = pts.reduce((s, p) => s + p.y, 0) / pts.length;
    expect(avgX).toBeCloseTo(0, 6);
    expect(avgY).toBeCloseTo(0, 6);
  });

  it("moving north decreases y (screen convention: north is up)", () => {
    const pts = projectLocal([[80.2, 13.0], [80.2, 13.01]]);
    expect(pts[1].y).toBeLessThan(pts[0].y);
  });

  it("moving east increases x", () => {
    const pts = projectLocal([[80.2, 13.0], [80.21, 13.0]]);
    expect(pts[1].x).toBeGreaterThan(pts[0].x);
  });

  it("is roughly metric: 0.01 degrees of latitude is about 1.1 km", () => {
    const pts = projectLocal([[80.2, 13.0], [80.2, 13.01]]);
    const dist = Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y);
    expect(dist).toBeGreaterThan(1000);
    expect(dist).toBeLessThan(1200);
  });
});
