import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { designApi, type DesignElement, type DesignOption, type DesignResult, type TrafficImpact } from "./api";
import RoadDashboard from "./RoadDashboard";

vi.mock("./api", async (orig) => ({
  ...(await orig<typeof import("./api")>()),
  designApi: { design: vi.fn(), explain: vi.fn(), explainOption: vi.fn(), downloadPdf: vi.fn(), setVerifiedWidth: vi.fn() },
}));

const e = (kind: DesignElement["kind"], cm: number, side: DesignElement["side"] = "left"): DesignElement => ({
  kind, label: kind, side, width_cm: cm, width_m: cm / 100, rule_ids: [], fallback_minimum: false,
});

const IMPACT: TrafficImpact = {
  sample_data: true,
  note: "Modelled estimate using a SAMPLE traffic volume and a standard congestion curve (BPR), not a real traffic count or a traffic simulation (SUMO).",
  sample_pcu: 900, sample_pcu_detail: "Sample demand detail. SAMPLE DATA.",
  length_m: 500,
  before: { lanes: 4, vc_ratio: 0.38, free_flow_kmh: 35, minutes: 1.1 },
  after: { lanes: 2, vc_ratio: 0.75, free_flow_kmh: 35, minutes: 1.3 },
  change_pct: 18.2,
};

const OPTION: DesignOption = {
  option_id: "traffic", name: "Traffic priority", summary: "As many lanes as fit.",
  elements: [e("footpath", 180), e("lane", 300), e("lane", 300), e("footpath", 180, "right")],
  omitted: [], notes: [],
  metrics: { lanes: 2, carriageway_m: 6, lane_width_m: 3, footpath_m: 1.8, has_cycle_track: false, has_trees: false, has_bus_bay: false, has_median: false },
  rule_ids: [], total_cm: 960, uses_fallback_minimums: false, impact: IMPACT,
};

const RESULT: DesignResult = {
  row_m: 9.6, row_cm: 960, road_class: "secondary", oneway: false, width_source: "estimated", context: [],
  auto_context: [], nearby: [], two_wheeler_pct: null, two_wheeler_detail: "",
  inputs: [],
  current: { elements: [e("footpath", 160), e("carriageway", 640), e("footpath", 160, "right")], total_cm: 960, note: "Approximate." },
  options: [OPTION], dropped: [], warnings: [], rules: {},
  segment: {
    seg_id: "1-2-0", name: "North Usman Road", road_width_m: 9.6, road_width_source: "estimated",
    geometry: { type: "LineString", coordinates: [[80.2345, 13.045], [80.236, 13.046]] },
  },
};

const props = { cityId: "chennai", segId: "1-2-0", optionId: "traffic", context: [], rowM: 9.6, onBack: vi.fn() };

beforeEach(() => {
  vi.mocked(designApi.design).mockReset().mockResolvedValue(RESULT);
  props.onBack.mockReset();
});

describe("RoadDashboard", () => {
  it("loads the design and shows the road and option name in the floating title", async () => {
    render(<RoadDashboard {...props} />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
    expect(await screen.findByText("North Usman Road — Traffic priority")).toBeInTheDocument();
    expect(designApi.design).toHaveBeenCalledWith("chennai", "1-2-0", { context: [], row_m: 9.6 });
  });

  it("shows the metrics, the flow maps and the sample travel-time panel", async () => {
    render(<RoadDashboard {...props} />);
    await screen.findByRole("region", { name: "Metrics" });
    expect(screen.getAllByTestId("road-flow-map")).toHaveLength(2);
    expect(screen.getByText("SAMPLE")).toBeInTheDocument();
    expect(screen.getByText(/SUMO/)).toBeInTheDocument();
    const metrics = within(screen.getByRole("region", { name: "Metrics" }));
    expect(metrics.getByText("3 m")).toBeInTheDocument(); // lane width
  });

  it("shows a single street-level scene with a Today/option toggle, defaulting to Today", async () => {
    render(<RoadDashboard {...props} />);
    await screen.findByRole("region", { name: "Metrics" });
    const detail = within(screen.getByRole("region", { name: "Street-level detail" }));
    await waitFor(() => expect(detail.getAllByTestId("road-scene-3d-unsupported")).toHaveLength(1));
    expect(detail.getByRole("button", { name: "Today" })).toHaveAttribute("aria-pressed", "true");
    expect(detail.getByRole("button", { name: "Traffic priority" })).toHaveAttribute("aria-pressed", "false");
  });

  it("switches the street-level scene to the option when its toggle button is clicked", async () => {
    const user = userEvent.setup();
    render(<RoadDashboard {...props} />);
    await screen.findByRole("region", { name: "Metrics" });
    const detail = within(screen.getByRole("region", { name: "Street-level detail" }));
    await user.click(detail.getByRole("button", { name: "Traffic priority" }));
    await waitFor(() => expect(detail.getAllByTestId("road-scene-3d-unsupported")).toHaveLength(1));
    expect(detail.getByRole("button", { name: "Traffic priority" })).toHaveAttribute("aria-pressed", "true");
  });

  it("goes back when the back link is clicked", async () => {
    const user = userEvent.setup();
    render(<RoadDashboard {...props} />);
    await screen.findByRole("region", { name: "Metrics" });
    await user.click(screen.getByText("← Back to design"));
    expect(props.onBack).toHaveBeenCalled();
  });

  it("shows an error if the design call fails", async () => {
    vi.mocked(designApi.design).mockRejectedValue(new Error("A rule file has a problem"));
    render(<RoadDashboard {...props} />);
    expect(await screen.findByText("A rule file has a problem")).toBeInTheDocument();
  });

  it("explains when the requested option isn't in the result", async () => {
    render(<RoadDashboard {...props} optionId="not-a-real-option" />);
    await waitFor(() => expect(screen.getByText(/isn't available at the current width/)).toBeInTheDocument());
  });
});
