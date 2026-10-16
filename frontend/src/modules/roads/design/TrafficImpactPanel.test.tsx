import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import TrafficImpactPanel from "./TrafficImpactPanel";
import type { TrafficImpact } from "./api";

const base: TrafficImpact = {
  sample_data: true,
  note: "Modelled estimate using a SAMPLE traffic volume and a standard congestion curve (BPR), not a real traffic count or a traffic simulation (SUMO).",
  sample_pcu: 900, sample_pcu_detail: "Sample demand detail. SAMPLE DATA.",
  length_m: 500,
  before: { lanes: 4, vc_ratio: 0.38, free_flow_kmh: 35, minutes: 1.1 },
  after: { lanes: 2, vc_ratio: 0.75, free_flow_kmh: 35, minutes: 1.3 },
  change_pct: 18.2,
};

describe("TrafficImpactPanel", () => {
  it("is always labelled SAMPLE and mentions it is not a simulation", () => {
    render(<TrafficImpactPanel impact={base} />);
    expect(screen.getByText("SAMPLE")).toBeInTheDocument();
    expect(screen.getByText(/SUMO/)).toBeInTheDocument();
  });

  it("shows lane counts and minutes before and after", () => {
    render(<TrafficImpactPanel impact={base} />);
    expect(screen.getByText("Today (4 lanes)")).toBeInTheDocument();
    expect(screen.getByText("This option (2 lanes)")).toBeInTheDocument();
    expect(screen.getByText("1.1 min")).toBeInTheDocument();
  });

  it("shows an up arrow and the percentage when travel time increases", () => {
    render(<TrafficImpactPanel impact={base} />);
    expect(screen.getByText("(↑ 18%)")).toBeInTheDocument();
  });

  it("shows a down arrow when travel time decreases", () => {
    render(<TrafficImpactPanel impact={{ ...base, change_pct: -12.5, after: { ...base.after, minutes: 0.9 } }} />);
    expect(screen.getByText("(↓ 13%)")).toBeInTheDocument();
  });

  it("singularises a one-lane count", () => {
    render(<TrafficImpactPanel impact={{ ...base, before: { ...base.before, lanes: 1 } }} />);
    expect(screen.getByText("Today (1 lane)")).toBeInTheDocument();
  });

  it("badges a real SUMO simulation distinctly from the SAMPLE formula estimate", () => {
    render(<TrafficImpactPanel impact={{ ...base, engine: "sumo", note: "Real SUMO microsimulation using a SAMPLE traffic volume." }} />);
    expect(screen.getByText("SUMO simulation")).toBeInTheDocument();
    expect(screen.queryByText("SAMPLE")).not.toBeInTheDocument();
    expect(screen.getByText(/Simulated travel-time impact/)).toBeInTheDocument();
  });
});
