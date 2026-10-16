import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import RoadFlowMap from "./RoadFlowMap";

const GEOMETRY = { type: "LineString" as const, coordinates: [[80.2345, 13.045], [80.236, 13.046], [80.2372, 13.0465]] as [number, number][] };

describe("RoadFlowMap", () => {
  it("renders the map and its label when geometry is available", () => {
    render(<RoadFlowMap geometry={GEOMETRY} vcRatio={0.4} label="Today" />);
    expect(screen.getByTestId("road-flow-map")).toBeInTheDocument();
    expect(screen.getByText("Today")).toBeInTheDocument();
  });

  it("falls back to a message instead of throwing when there is no geometry", () => {
    render(<RoadFlowMap geometry={null} vcRatio={0.4} label="Today" />);
    expect(screen.getByTestId("road-flow-map-unavailable")).toBeInTheDocument();
    expect(screen.queryByTestId("road-flow-map")).not.toBeInTheDocument();
  });

  it("falls back when the geometry has fewer than two points", () => {
    render(<RoadFlowMap geometry={{ type: "LineString", coordinates: [[80.2345, 13.045]] }} vcRatio={0.4} label="Today" />);
    expect(screen.getByTestId("road-flow-map-unavailable")).toBeInTheDocument();
  });

  it("accepts a null vcRatio (no demand data) without throwing", () => {
    render(<RoadFlowMap geometry={GEOMETRY} vcRatio={null} label="Today" />);
    expect(screen.getByTestId("road-flow-map")).toBeInTheDocument();
  });
});
