import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Segment, SegmentResponse } from "./api";
import RoadPanel from "./RoadPanel";

function segment(overrides: Partial<Segment> = {}): Segment {
  return {
    city_id: "chennai", seg_id: "1-2-0", osm_way_ids: [100], name: "North Usman Road",
    name_official: "NORTH USMAN ROAD", official_road_id: "R1", name_match: "same",
    display_name: "North Usman Road", display_name_source: "osm", ref: null, road_class: "secondary",
    oneway: false, lanes_osm: 2, osm_width_hint: null, sidewalk_osm: null, length_m: 83,
    width_m: 18, width_source: "estimated", width_source_detail: "Estimated: default for secondary, 18 m (UNCITED).",
    width_confidence: null, bbox: [0, 0, 0, 0], ...overrides,
  };
}

function response(overrides: Partial<SegmentResponse> = {}): SegmentResponse {
  return {
    segment: segment(), road: { name: "North Usman Road", segments: 44, length_m: 2802, bbox: [0, 0, 0, 0] },
    geometry_source: { name: "OpenStreetMap", licence: "ODbL 1.0", downloaded: "2026-09-25" },
    official_name_source: { name: "Greater Chennai Corporation", licence: "Public Domain", received: "2026-09-25" },
    linked_data: [], ...overrides,
  };
}

describe("RoadPanel", () => {
  it("shows a loading state", () => {
    render(<RoadPanel data={null} loading={true} error={null} onClose={vi.fn()} onZoomToRoad={vi.fn()} />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("shows an error", () => {
    render(<RoadPanel data={null} loading={false} error="boom" onClose={vi.fn()} onZoomToRoad={vi.fn()} />);
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("labels an unnamed road", () => {
    render(
      <RoadPanel data={response({ segment: segment({ display_name: null, name: null, name_official: null }) })}
        loading={false} error={null} onClose={vi.fn()} onZoomToRoad={vi.fn()} />,
    );
    expect(screen.getByRole("heading", { name: "Unnamed road" })).toBeInTheDocument();
  });

  it("shows the width with a confidence badge, and marks an estimate with a tilde", () => {
    render(<RoadPanel data={response()} loading={false} error={null} onClose={vi.fn()} onZoomToRoad={vi.fn()} />);
    expect(screen.getByText("~18 m")).toBeInTheDocument();
    expect(screen.getByText("Estimated")).toBeInTheDocument();
    expect(screen.getByText(/UNCITED/)).toBeInTheDocument();
  });

  it("does not add a tilde to a verified width", () => {
    render(
      <RoadPanel data={response({ segment: segment({ width_source: "verified", width_m: 24.5, width_source_detail: "Verified from survey." }) })}
        loading={false} error={null} onClose={vi.fn()} onZoomToRoad={vi.fn()} />,
    );
    expect(screen.getByText("24.5 m")).toBeInTheDocument();
    expect(screen.queryByText("~24.5 m")).not.toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument();
  });

  it("shows both the OSM and official name when they differ", () => {
    render(
      <RoadPanel data={response({ segment: segment({ name: "Bazulla Flyover", name_official: "Buzullah Road", name_match: "different" }) })}
        loading={false} error={null} onClose={vi.fn()} onZoomToRoad={vi.fn()} />,
    );
    expect(screen.getByText("Bazulla Flyover")).toBeInTheDocument();
    expect(screen.getByText("Buzullah Road")).toBeInTheDocument();
    expect(screen.getByText(/names differ/)).toBeInTheDocument();
  });

  it("shows the OSM width hint as a hint, not the width itself", () => {
    render(
      <RoadPanel data={response({ segment: segment({ osm_width_hint: "6" }) })}
        loading={false} error={null} onClose={vi.fn()} onZoomToRoad={vi.fn()} />,
    );
    expect(screen.getByText(/width=6/)).toBeInTheDocument();
    expect(screen.getByText(/HINT ONLY/i)).toBeInTheDocument();
  });

  it("lists data linked to the road, marking sample rows", () => {
    const data = response({
      linked_data: [{
        layer_id: "traffic_counts", label: "Traffic counts", color: "#7c3aed",
        summary_fields: [{ field: "cars", label: "Cars" }],
        rows: [{ import_id: "i1", row_no: 4, cars: 1200, is_sample: true }],
      }],
    });
    render(<RoadPanel data={data} loading={false} error={null} onClose={vi.fn()} onZoomToRoad={vi.fn()} />);
    expect(screen.getByText("Traffic counts")).toBeInTheDocument();
    expect(screen.getByText("SAMPLE")).toBeInTheDocument();
    expect(screen.getByText(/Cars: 1,200/)).toBeInTheDocument();
  });

  it("shows a confidence badge for a shaky measured width", () => {
    const data = response({ segment: segment({
      width_source: "measured", width_confidence: "unreliable",
      width_source_detail: "Measured from building footprints. (6 samples, IQR 11.3 m)",
    }) });
    render(<RoadPanel data={data} loading={false} error={null} onClose={vi.fn()} onZoomToRoad={vi.fn()} />);
    expect(screen.getByText("Unreliable")).toBeInTheDocument();
  });

  it("shows no confidence badge for an estimated width", () => {
    render(<RoadPanel data={response()} loading={false} error={null} onClose={vi.fn()} onZoomToRoad={vi.fn()} />);
    expect(screen.queryByText("Unreliable")).not.toBeInTheDocument();
    expect(screen.queryByText("Reliable")).not.toBeInTheDocument();
  });

  it("links to Google Street View at exactly where the road was clicked", () => {
    const data = response({ segment: segment({ bbox: [80.24, 13.04, 80.26, 13.06] }) });
    render(<RoadPanel data={data} loading={false} error={null} onClose={vi.fn()} onZoomToRoad={vi.fn()}
      clickLngLat={{ lng: 80.2583, lat: 13.0417 }} />);
    const link = screen.getByRole("link", { name: /Open in Google Street View/ });
    expect(link).toHaveAttribute("href", "https://www.google.com/maps?layer=c&cbll=13.0417,80.2583&cbp=12,0,,0,0&z=18");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("falls back to the segment's midpoint when there's no click point", () => {
    const data = response({ segment: segment({ bbox: [80.24, 13.04, 80.26, 13.06] }) });
    render(<RoadPanel data={data} loading={false} error={null} onClose={vi.fn()} onZoomToRoad={vi.fn()} />);
    const link = screen.getByRole("link", { name: /Open in Google Street View/ });
    expect(link).toHaveAttribute("href", "https://www.google.com/maps?layer=c&cbll=13.05,80.25&cbp=12,0,,0,0&z=18");
  });

  it("calls onClose and onZoomToRoad", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const onZoom = vi.fn();
    render(<RoadPanel data={response()} loading={false} error={null} onClose={onClose} onZoomToRoad={onZoom} />);
    await user.click(screen.getByRole("button", { name: "show" }));
    expect(onZoom).toHaveBeenCalled();
    await user.click(screen.getByLabelText("Close"));
    expect(onClose).toHaveBeenCalled();
  });
});
