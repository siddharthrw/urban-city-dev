import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import RoadScene3D from "./RoadScene3D";
import type { DesignElement } from "./api";

const ELEMENTS: DesignElement[] = [
  { kind: "footpath", label: "Footpath", side: "left", width_cm: 180, width_m: 1.8, rule_ids: [], fallback_minimum: false },
  { kind: "lane", label: "Lane", side: "centre", width_cm: 300, width_m: 3, rule_ids: [], fallback_minimum: false },
  { kind: "footpath", label: "Footpath", side: "right", width_cm: 180, width_m: 1.8, rule_ids: [], fallback_minimum: false },
];

const GEOMETRY = { type: "LineString" as const, coordinates: [[80.2345, 13.045], [80.236, 13.046], [80.2372, 13.0465]] as [number, number][] };

describe("RoadScene3D", () => {
  // jsdom has no WebGL context, so this exercises the real fallback path (not a mock) rather
  // than constructing a THREE.WebGLRenderer, which would throw in this environment.
  it("falls back to a text message instead of throwing when WebGL is unavailable", () => {
    render(<RoadScene3D elements={ELEMENTS} rowCm={660} geometry={GEOMETRY} label="Today" />);
    expect(screen.getByTestId("road-scene-3d-unsupported")).toBeInTheDocument();
    expect(screen.getByText(/needs a browser with WebGL/)).toBeInTheDocument();
  });

  it("does not render the canvas container when unsupported", () => {
    render(<RoadScene3D elements={ELEMENTS} rowCm={660} geometry={GEOMETRY} label="Today" />);
    expect(screen.queryByTestId("road-scene-3d")).not.toBeInTheDocument();
  });

  it("falls back gracefully with no geometry too", () => {
    render(<RoadScene3D elements={ELEMENTS} rowCm={660} geometry={null} label="Today" />);
    expect(screen.getByTestId("road-scene-3d-unsupported")).toBeInTheDocument();
  });
});
