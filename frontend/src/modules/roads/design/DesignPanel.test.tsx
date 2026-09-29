import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { designApi, type DesignElement, type DesignOption, type DesignResult } from "./api";
import DesignPanel from "./DesignPanel";

vi.mock("./api", async (orig) => ({
  ...(await orig<typeof import("./api")>()),
  designApi: { design: vi.fn(), explain: vi.fn(), explainOption: vi.fn(), downloadPdf: vi.fn(), setVerifiedWidth: vi.fn() },
}));

const e = (kind: DesignElement["kind"], cm: number, side: DesignElement["side"] = "left"): DesignElement => ({
  kind, label: kind, side, width_cm: cm, width_m: cm / 100, rule_ids: ["footpath_min_width"], fallback_minimum: false,
});

const OPTION: DesignOption = {
  option_id: "traffic", name: "Traffic priority", summary: "As many lanes as fit.",
  elements: [e("footpath", 180), e("lane", 300), e("lane", 300), e("footpath", 180, "right")],
  omitted: [{ kind: "median", reason: "Median left out so the option fits in 12 m." }],
  notes: ["Lanes reduced from 4 to 2 so the option fits."],
  metrics: { lanes: 2, carriageway_m: 6, lane_width_m: 3, footpath_m: 1.8, has_cycle_track: false, has_trees: false, has_bus_bay: false, has_median: false },
  rule_ids: ["footpath_min_width"], total_cm: 960, uses_fallback_minimums: false,
};

const RESULT: DesignResult = {
  row_m: 9.6, row_cm: 960, road_class: "secondary", oneway: false, width_source: "estimated", context: [],
  auto_context: [], nearby: [],
  inputs: [{ name: "Right-of-way", value: "9.6 m", source: "estimated", detail: "Typical width for this type of road (not measured)." },
    { name: "Lanes needed", value: "2 per direction", source: "default", detail: "No traffic count linked." }],
  options: [OPTION],
  dropped: [{ option_id: "balanced", name: "Balanced (cycle track + shade)", reason: "Needs at least 16 m, but the road is 9.6 m." }],
  warnings: ["The road width is an ESTIMATE (a typical width).", "Dimensions come from PLACEHOLDER rules (UNCITED guesses)."],
  rules: { footpath_min_width: { statement: "UNCITED placeholder: footpaths at least 1.8 m.", authority: "placeholder", source: "Placeholder (uncited)", quote: null, page: null } },
  segment: { seg_id: "1-2-0", name: "North Usman Road", road_width_m: 9.6, road_width_source: "estimated" },
};

const props = { cityId: "chennai", segId: "1-2-0", roadWidthM: 9.6, roadWidthSource: "estimated" as const, onBack: vi.fn(), onClose: vi.fn() };

beforeEach(() => {
  vi.mocked(designApi.design).mockReset().mockResolvedValue(RESULT);
  vi.mocked(designApi.explain).mockReset();
  vi.mocked(designApi.explainOption).mockReset();
  vi.mocked(designApi.downloadPdf).mockReset();
  props.onBack.mockReset();
  props.onClose.mockReset();
});

describe("DesignPanel", () => {
  it("designs automatically on open, using the road's own width", async () => {
    render(<DesignPanel {...props} />);
    expect(await screen.findByText("Traffic priority")).toBeInTheDocument();
    expect(designApi.design).toHaveBeenCalledWith("chennai", "1-2-0", { context: [], row_m: 9.6 });
    expect(screen.getByText("Design: North Usman Road")).toBeInTheDocument();
  });

  it("draws each option's cross-section to the road's width", async () => {
    render(<DesignPanel {...props} />);
    await screen.findByText("Traffic priority");
    expect(screen.getAllByTestId("element")).toHaveLength(4);
    expect(screen.getByText("9.6 m right-of-way")).toBeInTheDocument();
  });

  it("shows the warnings, including the estimate and placeholder-rule warnings", async () => {
    render(<DesignPanel {...props} />);
    const warnings = await screen.findByRole("list", { name: "Warnings" });
    expect(within(warnings).getByText(/ESTIMATE/)).toBeInTheDocument();
    expect(within(warnings).getByText(/PLACEHOLDER/)).toBeInTheDocument();
  });

  it("says which options are impossible and why", async () => {
    render(<DesignPanel {...props} />);
    const dropped = await screen.findByRole("region", { name: "Dropped options" });
    expect(within(dropped).getByText(/Balanced/)).toBeInTheDocument();
    expect(within(dropped).getByText(/Needs at least 16 m/)).toBeInTheDocument();
  });

  it("shows notes, omitted elements and metrics for an option", async () => {
    render(<DesignPanel {...props} />);
    const card = await screen.findByRole("region", { name: "Traffic priority" });
    expect(within(card).getByText(/Lanes reduced from 4 to 2/)).toBeInTheDocument();
    expect(within(card).getByText(/Median left out/)).toBeInTheDocument();
    expect(within(card).getByText("1.8 m each side")).toBeInTheDocument();
  });

  it("lists the rules applied with their statement and an uncited badge", async () => {
    render(<DesignPanel {...props} />);
    const card = await screen.findByRole("region", { name: "Traffic priority" });
    await userEvent.click(within(card).getByText(/Rules applied \(1\)/));
    expect(within(card).getByText("footpath_min_width")).toBeInTheDocument();
    expect(within(card).getByText(/UNCITED placeholder: footpaths/)).toBeInTheDocument();
    expect(within(card).getByText("Placeholder — uncited")).toBeInTheDocument();
  });

  it("shows where each input came from", async () => {
    render(<DesignPanel {...props} />);
    await screen.findByText("Traffic priority");
    await userEvent.click(screen.getByText(/What this design used/));
    expect(screen.getByText("Lanes needed")).toBeInTheDocument();
    expect(screen.getByText("default")).toBeInTheDocument();
    expect(screen.getByText(/No traffic count linked/)).toBeInTheDocument();
  });

  it("re-designs with the ticked context and a changed width", async () => {
    const user = userEvent.setup();
    render(<DesignPanel {...props} />);
    await screen.findByText("Traffic priority");
    await user.click(screen.getByLabelText("School nearby"));
    await user.click(screen.getByLabelText("Bus route"));
    const width = screen.getByLabelText("Right-of-way width in metres");
    await user.clear(width);
    await user.type(width, "18");
    await user.click(screen.getByRole("button", { name: "Update design" }));
    await waitFor(() => expect(designApi.design).toHaveBeenLastCalledWith("chennai", "1-2-0",
      { context: ["school_nearby", "bus_route"], row_m: 18 }));
  });

  it("rejects an impossible width without calling the server", async () => {
    const user = userEvent.setup();
    render(<DesignPanel {...props} />);
    await screen.findByText("Traffic priority");
    vi.mocked(designApi.design).mockClear();
    const width = screen.getByLabelText("Right-of-way width in metres");
    await user.clear(width);
    await user.type(width, "abc");
    await user.click(screen.getByRole("button", { name: "Update design" }));
    expect(screen.getByText(/between 3 and 150 metres/)).toBeInTheDocument();
    expect(designApi.design).not.toHaveBeenCalled();
  });

  it("shows a server error", async () => {
    vi.mocked(designApi.design).mockRejectedValue(new Error("A rule file has a problem"));
    render(<DesignPanel {...props} />);
    expect(await screen.findByText("A rule file has a problem")).toBeInTheDocument();
  });

  it("goes back to the road details and closes", async () => {
    const user = userEvent.setup();
    render(<DesignPanel {...props} />);
    await screen.findByText("Traffic priority");
    await user.click(screen.getByText("← Road details"));
    expect(props.onBack).toHaveBeenCalled();
    await user.click(screen.getByLabelText("Close design"));
    expect(props.onClose).toHaveBeenCalled();
  });

  it("explains an empty result rather than showing nothing", async () => {
    vi.mocked(designApi.design).mockResolvedValue({ ...RESULT, options: [], warnings: ["No layout satisfies the rules at this width."] });
    render(<DesignPanel {...props} />);
    expect(await screen.findByText(/No layout satisfies the rules/)).toBeInTheDocument();
    expect(screen.getByText(/Needs at least 16 m/)).toBeInTheDocument();
  });

  it("shows an Export PDF button and a per-option Explain button after design loads", async () => {
    render(<DesignPanel {...props} />);
    await screen.findByText("Traffic priority");
    expect(screen.getByRole("button", { name: "Export PDF" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Explain Traffic priority" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Explain options" })).not.toBeInTheDocument();
  });

  it("calls explainOption and shows the explanation below the diagram", async () => {
    const user = userEvent.setup();
    vi.mocked(designApi.explainOption).mockResolvedValue({
      explanation: "This layout maximises vehicle throughput on the road.",
      warnings: [],
    });
    render(<DesignPanel {...props} />);
    await screen.findByText("Traffic priority");
    await user.click(screen.getByRole("button", { name: "Explain Traffic priority" }));
    await waitFor(() =>
      expect(screen.getByText("This layout maximises vehicle throughput on the road.")).toBeInTheDocument()
    );
    expect(designApi.explainOption).toHaveBeenCalledWith("chennai", "1-2-0", "traffic", { context: [], row_m: 9.6 });
    // Regenerate button replaces the Explain button
    expect(screen.getByRole("button", { name: /Regenerate/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Explain Traffic priority" })).not.toBeInTheDocument();
  });

  it("shows per-option explanation warnings from the LLM", async () => {
    const user = userEvent.setup();
    vi.mocked(designApi.explainOption).mockResolvedValue({
      explanation: "Some text.",
      warnings: ["Explanation cited unknown rule IDs: irc_103."],
    });
    render(<DesignPanel {...props} />);
    await screen.findByText("Traffic priority");
    await user.click(screen.getByRole("button", { name: "Explain Traffic priority" }));
    await waitFor(() => expect(screen.getByText(/irc_103/)).toBeInTheDocument());
  });

  it("shows an error in the option card when the explain call fails", async () => {
    const user = userEvent.setup();
    vi.mocked(designApi.explainOption).mockRejectedValue(new Error("LLM unavailable"));
    render(<DesignPanel {...props} />);
    await screen.findByText("Traffic priority");
    await user.click(screen.getByRole("button", { name: "Explain Traffic priority" }));
    await waitFor(() => expect(screen.getByText("LLM unavailable")).toBeInTheDocument());
    // Explain button remains (so the user can retry)
    expect(screen.getByRole("button", { name: "Explain Traffic priority" })).toBeInTheDocument();
  });

  it("calls downloadPdf when Export PDF is clicked", async () => {
    const user = userEvent.setup();
    vi.mocked(designApi.downloadPdf).mockResolvedValue(new Blob(["%PDF-1.4"], { type: "application/pdf" }));
    // stub browser download API
    const createObjectURL = vi.fn().mockReturnValue("blob:test");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    render(<DesignPanel {...props} />);
    await screen.findByText("Traffic priority");
    await user.click(screen.getByRole("button", { name: "Export PDF" }));
    await waitFor(() => expect(designApi.downloadPdf).toHaveBeenCalledWith("chennai", "1-2-0", {
      row_m: 9.6, context: [],
    }));
    vi.unstubAllGlobals();
  });
});
