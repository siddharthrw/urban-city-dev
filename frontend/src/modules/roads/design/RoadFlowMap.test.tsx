import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import RoadFlowMap from "./RoadFlowMap";
import type { DesignElement } from "./api";

const GEOMETRY = { type: "LineString" as const, coordinates: [[80.2345, 13.045], [80.236, 13.046], [80.2372, 13.0465]] as [number, number][] };

const el = (kind: DesignElement["kind"]): DesignElement => ({
  kind, label: kind, side: "left", width_cm: 200, width_m: 2, rule_ids: [], fallback_minimum: false,
});
const NO_TREES = [el("footpath"), el("carriageway"), el("footpath")];
const WITH_TREES = [el("footpath"), el("tree_strip"), el("cycle_track"), el("lane"), el("lane"), el("cycle_track"), el("tree_strip"), el("footpath")];

describe("RoadFlowMap", () => {
  it("renders the map and its label when geometry is available", () => {
    render(<RoadFlowMap geometry={GEOMETRY} elements={NO_TREES} vcRatio={0.4} label="Today" />);
    expect(screen.getByTestId("road-flow-map")).toBeInTheDocument();
    expect(screen.getByText("Today")).toBeInTheDocument();
  });

  it("falls back to a message instead of throwing when there is no geometry", () => {
    render(<RoadFlowMap geometry={null} elements={NO_TREES} vcRatio={0.4} label="Today" />);
    expect(screen.getByTestId("road-flow-map-unavailable")).toBeInTheDocument();
    expect(screen.queryByTestId("road-flow-map")).not.toBeInTheDocument();
  });

  it("falls back when the geometry has fewer than two points", () => {
    render(<RoadFlowMap geometry={{ type: "LineString", coordinates: [[80.2345, 13.045]] }} elements={NO_TREES} vcRatio={0.4} label="Today" />);
    expect(screen.getByTestId("road-flow-map-unavailable")).toBeInTheDocument();
  });

  it("accepts a null vcRatio (no demand data) without throwing", () => {
    render(<RoadFlowMap geometry={GEOMETRY} elements={NO_TREES} vcRatio={null} label="Today" />);
    expect(screen.getByTestId("road-flow-map")).toBeInTheDocument();
  });

  it("doesn't claim trees, cycle track or footpath in the legend when this scenario has none", () => {
    render(<RoadFlowMap geometry={GEOMETRY} elements={[el("carriageway")]} vcRatio={0.4} label="Today" />);
    const legend = screen.getByLabelText("Legend");
    expect(legend).not.toHaveTextContent("Trees");
    expect(legend).not.toHaveTextContent("Cycle track");
    expect(legend).not.toHaveTextContent("Footpath");
  });

  it("shows footpath in the legend when this scenario's current state has one, even with no trees", () => {
    render(<RoadFlowMap geometry={GEOMETRY} elements={NO_TREES} vcRatio={0.4} label="Today" />);
    const legend = screen.getByLabelText("Legend");
    expect(legend).toHaveTextContent("Footpath");
    expect(legend).not.toHaveTextContent("Trees");
  });

  it("shows trees, cycle track and footpath in the legend when this option has them", () => {
    render(<RoadFlowMap geometry={GEOMETRY} elements={WITH_TREES} vcRatio={0.4} label="This option" />);
    const legend = screen.getByLabelText("Legend");
    expect(legend).toHaveTextContent("Trees");
    expect(legend).toHaveTextContent("Cycle track");
    expect(legend).toHaveTextContent("Footpath");
  });
});
