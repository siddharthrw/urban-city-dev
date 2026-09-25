import type * as maplibregl from "maplibre-gl";
import { CONFIDENCE } from "../../core/provenance";
import type { LayerInfo } from "../../core/api";

export const SOURCE_ID = "roads";
const LINE = "roads-line";
const ROAD_HL = "roads-road-highlight";
const SEG_HL = "roads-segment-highlight";
const CLICK_TOLERANCE_PX = 5;
// Area covered by RoadPanel (w-96 + margins, typical height), in CSS pixels.
const PANEL_W = 420;
const PANEL_H = 360;

const MAJOR = ["motorway", "trunk", "primary"];
const MID = ["secondary", "tertiary", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"];

// Thicker lines for bigger roads, growing with zoom.
const lineWidth = (scale: number): maplibregl.ExpressionSpecification => [
  "interpolate", ["linear"], ["zoom"],
  10, ["*", scale, ["case", ["in", ["get", "road_class"], ["literal", MAJOR]], 2, ["in", ["get", "road_class"], ["literal", MID]], 1.2, 0.5]],
  15, ["*", scale, ["case", ["in", ["get", "road_class"], ["literal", MAJOR]], 7, ["in", ["get", "road_class"], ["literal", MID]], 5, 2.5]],
  18, ["*", scale, ["case", ["in", ["get", "road_class"], ["literal", MAJOR]], 16, ["in", ["get", "road_class"], ["literal", MID]], 12, 7]],
];

export function addRoadsLayer(map: maplibregl.Map, layer: LayerInfo) {
  if (map.getSource(SOURCE_ID) || !layer.tiles_url) return;
  map.addSource(SOURCE_ID, {
    type: "vector",
    url: `pmtiles://${window.location.origin}${layer.tiles_url}`,
    promoteId: "seg_id",
  });
  const common = { source: SOURCE_ID, "source-layer": "roads" } as const;

  map.addLayer({
    id: LINE, type: "line", ...common,
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": ["match", ["get", "width_source"],
        "verified", CONFIDENCE.verified.color,
        "measured", CONFIDENCE.measured.color,
        CONFIDENCE.estimated.color],
      "line-width": lineWidth(1),
      "line-opacity": 0.9,
    },
  });
  // All segments of the selected road name.
  map.addLayer({
    id: ROAD_HL, type: "line", ...common,
    filter: ["==", ["get", "display_name"], ""],
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": "#60a5fa", "line-width": lineWidth(1.6), "line-opacity": 0.8 },
  });
  // The clicked segment.
  map.addLayer({
    id: SEG_HL, type: "line", ...common,
    filter: ["==", ["get", "seg_id"], ""],
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": "#1d4ed8", "line-width": lineWidth(2) },
  });
}

export function setRoadsVisible(map: maplibregl.Map, visible: boolean) {
  for (const id of [LINE, ROAD_HL, SEG_HL]) {
    if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
  }
}

export function highlight(map: maplibregl.Map, segId: string | null, roadName: string | null) {
  if (!map.getLayer(SEG_HL)) return;
  map.setFilter(SEG_HL, ["==", ["get", "seg_id"], segId ?? ""]);
  map.setFilter(ROAD_HL, ["==", ["get", "display_name"], roadName ?? ""]);
}

/** The road segment under a screen point, with a few pixels of tolerance (residential streets are thin). */
export function roadAt(map: maplibregl.Map, p: { x: number; y: number }): string | null {
  if (!map.getLayer(LINE)) return null;
  const t = CLICK_TOLERANCE_PX;
  const feats = map.queryRenderedFeatures([[p.x - t, p.y - t], [p.x + t, p.y + t]], { layers: [LINE] });
  return feats.length ? String(feats[0].properties.seg_id) : null;
}

/** The details panel sits top-right; if the clicked spot is underneath it, slide the map left. */
export function keepClearOfPanel(map: maplibregl.Map, p: { x: number; y: number }) {
  const w = map.getCanvas().clientWidth;
  if (p.x > w - PANEL_W && p.y < PANEL_H) {
    map.panBy([p.x - (w - PANEL_W) / 2, 0], { duration: 400 });
  }
}

