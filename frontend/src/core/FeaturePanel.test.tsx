import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { LayerInfo } from "./api";
import FeaturePanel from "./FeaturePanel";
import type { LayerType } from "./inbox/api";

const LAYER: LayerInfo = {
  layer_id: "bus_stops", topic: "surroundings", label: "Bus stops", geometry_type: "Point",
  feature_count: 5, built_at: "2026-09-25", id_column: null, tiles_url: null, tiles: null,
  kind: "imported", color: "#ea580c", summary_fields: ["stop_name"], has_sample_data: true,
  sources: [{ source_id: "s1", name: "SAMPLE_bus_stops.kml", origin: "uploaded", licence: "test", received_at: "2026-09-25" }],
};

const LAYER_TYPE: LayerType = {
  layer_id: "bus_stops", topic: "surroundings", label: "Bus stops", description: "", color: "#ea580c", effects: [],
  fields: [
    { field: "stop_name", label: "Stop name", type: "string" },
    { field: "routes", label: "Routes", type: "string" },
    { field: "daily_boardings", label: "Daily boardings", type: "int" },
  ],
};

describe("FeaturePanel", () => {
  it("shows labelled field values, hiding system columns", () => {
    render(
      <FeaturePanel layer={LAYER} layerType={LAYER_TYPE} sourceName="SAMPLE_bus_stops.kml" onClose={vi.fn()}
        properties={{
          import_id: "i1", source_id: "s1", city_id: "chennai", row_no: 1, is_sample: false,
          seg_id: "1-2-0", seg_ids: ["1-2-0"], link_method: "location", road_name_matched: "North Usman Road",
          link_distance_m: 2.8, link_note: null, latitude: 13.05, longitude: 80.23,
          stop_name: "Test stop A", routes: "SAMPLE-1, SAMPLE-2", daily_boardings: 1200,
        }} />,
    );
    expect(screen.getByText("Test stop A")).toBeInTheDocument();
    expect(screen.getByText("SAMPLE-1, SAMPLE-2")).toBeInTheDocument();
    expect(screen.getByText("1,200")).toBeInTheDocument();
    expect(screen.getByText("Stop name")).toBeInTheDocument();
    expect(screen.queryByText("import_id")).not.toBeInTheDocument();
    expect(screen.queryByText("i1")).not.toBeInTheDocument();
  });

  it("shows a SAMPLE badge only for sample rows", () => {
    const { rerender } = render(
      <FeaturePanel layer={LAYER} layerType={LAYER_TYPE} sourceName={undefined} onClose={vi.fn()}
        properties={{ is_sample: true, row_no: 1 }} />,
    );
    expect(screen.getByText("SAMPLE: made-up test data")).toBeInTheDocument();

    rerender(
      <FeaturePanel layer={LAYER} layerType={LAYER_TYPE} sourceName={undefined} onClose={vi.fn()}
        properties={{ is_sample: false, row_no: 1 }} />,
    );
    expect(screen.queryByText("SAMPLE: made-up test data")).not.toBeInTheDocument();
  });

  it("describes the road link, including the distance and note", () => {
    render(
      <FeaturePanel layer={LAYER} layerType={LAYER_TYPE} sourceName={undefined} onClose={vi.fn()}
        properties={{
          source_id: "s1", seg_ids: ["1-2-0", "2-3-0"], road_name_matched: "North Usman Road", link_method: "name_fuzzy",
          link_distance_m: null, link_note: "Spelling differs; matched 'North Usman Road' (97%).", row_no: 7,
        }} />,
    );
    expect(screen.getByText(/Linked to/)).toBeInTheDocument();
    expect(screen.getAllByText(/North Usman Road/).length).toBeGreaterThan(0);
    expect(screen.getByText(/2 segments/)).toBeInTheDocument();
    expect(screen.getByText(/Spelling differs/)).toBeInTheDocument();
  });

  it("says when a row is not linked to a road", () => {
    render(<FeaturePanel layer={LAYER} layerType={LAYER_TYPE} sourceName={undefined} onClose={vi.fn()} properties={{ row_no: 5 }} />);
    expect(screen.getByText("Not linked to a road.")).toBeInTheDocument();
  });

  it("calls onClose", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<FeaturePanel layer={LAYER} layerType={LAYER_TYPE} sourceName={undefined} onClose={onClose} properties={{ row_no: 1 }} />);
    await user.click(screen.getByLabelText("Close"));
    expect(onClose).toHaveBeenCalled();
  });
});
