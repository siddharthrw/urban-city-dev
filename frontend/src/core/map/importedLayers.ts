// Imported (small) layers: GeoJSON for the current map view, reloaded as the map moves.
// Points -> circles, lines (incl. rows placed on a road by name) -> lines, areas -> fills.
import type * as maplibregl from "maplibre-gl";
import { api, type LayerInfo } from "../api";

const DEFAULT_COLOR = "#475569";
const ids = (layerId: string) => ({
  source: `imp-${layerId}`,
  line: `imp-${layerId}-line`,
  fill: `imp-${layerId}-fill`,
  circle: `imp-${layerId}-circle`,
});

export function importedLayerIds(layers: LayerInfo[]): string[] {
  return layers.filter((l) => l.kind === "imported").flatMap((l) => {
    const i = ids(l.layer_id);
    return [i.circle, i.line, i.fill];
  });
}

/** Add sources + style layers for every imported layer (idempotent). */
export function addImportedLayers(map: maplibregl.Map, layers: LayerInfo[]) {
  for (const l of layers.filter((x) => x.kind === "imported")) {
    const i = ids(l.layer_id);
    const color = l.color ?? DEFAULT_COLOR;
    if (map.getSource(i.source)) continue;
    map.addSource(i.source, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    map.addLayer({
      id: i.fill, type: "fill", source: i.source,
      filter: ["==", ["geometry-type"], "Polygon"],
      paint: { "fill-color": color, "fill-opacity": 0.25, "fill-outline-color": color },
    });
    map.addLayer({
      id: i.line, type: "line", source: i.source,
      filter: ["==", ["geometry-type"], "LineString"],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": color,
        "line-opacity": 0.55,
        "line-width": ["interpolate", ["linear"], ["zoom"], 11, 4, 16, 12],
        // Made-up SAMPLE data is dashed, so it can't be mistaken for real data.
        "line-dasharray": ["case", ["==", ["get", "is_sample"], true], ["literal", [1, 1]], ["literal", [1, 0]]],
      },
    });
    map.addLayer({
      id: i.circle, type: "circle", source: i.source,
      filter: ["==", ["geometry-type"], "Point"],
      paint: {
        "circle-color": color,
        // Dots grow from 2 px (city overview) to 7 px (street level).
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 2, 14, 5, 17, 7],
        // Fade from near-invisible at city level to full opacity at neighbourhood level.
        "circle-opacity": ["interpolate", ["linear"], ["zoom"], 10, 0.15, 13, 0.7, 15, 0.9],
        "circle-stroke-color": ["case", ["==", ["get", "is_sample"], true], "#f97316", "#ffffff"],
        // Stroke only appears when zoomed in enough to matter.
        "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 12, 0, 14, 1.5],
        "circle-stroke-opacity": ["interpolate", ["linear"], ["zoom"], 12, 0, 14, 0.8],
      },
    });
  }
}

export function setImportedVisible(map: maplibregl.Map, layerId: string, visible: boolean) {
  const i = ids(layerId);
  for (const id of [i.fill, i.line, i.circle]) {
    if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
  }
}

/** Load features for the current view into each visible imported layer. */
export async function refreshImported(map: maplibregl.Map, cityId: string, layers: LayerInfo[], visible: Record<string, boolean>) {
  const b = map.getBounds();
  const bbox: [number, number, number, number] = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()];
  await Promise.all(
    layers
      .filter((l) => l.kind === "imported" && visible[l.layer_id] !== false)
      .map(async (l) => {
        const src = map.getSource(ids(l.layer_id).source) as maplibregl.GeoJSONSource | undefined;
        if (!src) return;
        try {
          src.setData(await api.features(cityId, l.layer_id, bbox));
        } catch {
          /* a failed refresh keeps the previous data on screen */
        }
      }),
  );
}

export type ImportedHit = { layerId: string; properties: Record<string, unknown>; isPoint: boolean };

export function queryImported(map: maplibregl.Map, layers: LayerInfo[], p: { x: number; y: number }): ImportedHit | null {
  const styleIds = importedLayerIds(layers).filter((id) => map.getLayer(id));
  if (!styleIds.length) return null;
  const t = 6;
  const hits = map.queryRenderedFeatures([[p.x - t, p.y - t], [p.x + t, p.y + t]], { layers: styleIds });
  if (!hits.length) return null;
  // Points are the most specific target; prefer them over lines drawn along a whole road.
  const best = hits.find((h) => h.geometry.type === "Point") ?? hits[0];
  const layerId = best.layer.id.replace(/^imp-/, "").replace(/-(line|fill|circle)$/, "");
  return { layerId, properties: best.properties as Record<string, unknown>, isPoint: best.geometry.type === "Point" };
}
