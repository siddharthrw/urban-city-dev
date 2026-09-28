import { useCallback, useEffect, useRef, useState } from "react";
import type * as maplibregl from "maplibre-gl";
import { api, type City, type Health, type LayerInfo, type SystemInfo, type Topic } from "./core/api";
import FeaturePanel from "./core/FeaturePanel";
import { inboxApi, type LayerType } from "./core/inbox/api";
import InboxPage from "./core/inbox/InboxPage";
import RulesPage from "./core/rules/RulesPage";
import CityMap from "./core/map/CityMap";
import {
  addImportedLayers, queryImported, refreshImported, setImportedVisible, type ImportedHit,
} from "./core/map/importedLayers";
import { CONFIDENCE, type WidthSource } from "./core/provenance";
import { roadsApi, type SearchHit, type SegmentResponse } from "./modules/roads/api";
import { addRoadsLayer, highlight, keepClearOfPanel, roadAt, setRoadsVisible } from "./modules/roads/roadsLayer";
import DesignPanel from "./modules/roads/design/DesignPanel";
import RoadPanel from "./modules/roads/RoadPanel";
import RoadSearch from "./modules/roads/RoadSearch";

type Bbox = [number, number, number, number];
type Page = "map" | "inbox" | "rules";

export default function App() {
  const [page, setPage] = useState<Page>("map");
  const [cities, setCities] = useState<City[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [layers, setLayers] = useState<LayerInfo[]>([]);
  const [layerTypes, setLayerTypes] = useState<LayerType[]>([]);
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [health, setHealth] = useState<Health | null>(null);
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [map, setMap] = useState<maplibregl.Map | null>(null);

  const [segId, setSegId] = useState<string | null>(null);
  const [seg, setSeg] = useState<SegmentResponse | null>(null);
  const [segLoading, setSegLoading] = useState(false);
  const [segError, setSegError] = useState<string | null>(null);
  const [clickLngLat, setClickLngLat] = useState<{ lng: number; lat: number } | null>(null);
  const [pickedRoad, setPickedRoad] = useState<SearchHit | null>(null);
  const [feature, setFeature] = useState<ImportedHit | null>(null);
  const [dataVersion, setDataVersion] = useState(0);
  const [designing, setDesigning] = useState(false);

  const city = cities[0];
  const layersRef = useRef(layers);
  layersRef.current = layers;
  const visibleRef = useRef(visible);
  visibleRef.current = visible;

  useEffect(() => {
    Promise.all([api.cities(), api.topics(), api.health(), api.system(), inboxApi.layerTypes()])
      .then(([c, t, h, s, lt]) => {
        setCities(c);
        setTopics(t);
        setHealth(h);
        setSystem(s);
        setLayerTypes(lt);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  // Layer list: on start, and again whenever the inbox changes data.
  useEffect(() => {
    if (city) api.layers(city.city_id).then(setLayers).catch((e: Error) => setError(e.message));
  }, [city, dataVersion]);

  // Put layers on the map: roads first (bottom), imported data on top.
  useEffect(() => {
    if (!map || !city) return;
    const roads = layers.find((l) => l.layer_id === "roads");
    if (roads) addRoadsLayer(map, roads);
    addImportedLayers(map, layers);
    refreshImported(map, city.city_id, layers, visibleRef.current);
  }, [map, layers, city]);

  // Reload imported features for the view after panning/zooming (debounced).
  useEffect(() => {
    if (!map || !city) return;
    let t: ReturnType<typeof setTimeout>;
    const onMove = () => {
      clearTimeout(t);
      t = setTimeout(() => refreshImported(map, city.city_id, layersRef.current, visibleRef.current), 250);
    };
    map.on("moveend", onMove);
    return () => {
      clearTimeout(t);
      map.off("moveend", onMove);
    };
  }, [map, city]);

  // Tiles bake in road widths: after an import that changes widths, reload the roads source.
  useEffect(() => {
    if (!map || dataVersion === 0) return;
    const src = map.getSource("roads") as maplibregl.VectorTileSource | undefined;
    const roads = layers.find((l) => l.layer_id === "roads");
    if (src && roads?.tiles_url) src.setUrl(`pmtiles://${window.location.origin}${roads.tiles_url}?v=${dataVersion}`);
  }, [map, dataVersion, layers]);

  useEffect(() => {
    if (!map) return;
    for (const l of layers) {
      const on = visible[l.layer_id] !== false;
      if (l.layer_id === "roads") setRoadsVisible(map, on);
      else setImportedVisible(map, l.layer_id, on);
    }
    if (city) refreshImported(map, city.city_id, layers, visible);
  }, [map, visible, layers, city]);

  // One click handler. Priority: imported points (a bus stop), then the road, then imported
  // lines/areas (rows placed along a whole road by name would otherwise hide the road itself;
  // the road panel lists them anyway).
  useEffect(() => {
    if (!map) return;
    const click = (e: maplibregl.MapMouseEvent) => {
      const hit = queryImported(map, layersRef.current, e.point);
      const id = hit?.isPoint ? null : roadAt(map, e.point);
      if (hit && !id) {
        setFeature(hit);
        setSegId(null);
        keepClearOfPanel(map, e.point);
        return;
      }
      setFeature(null);
      setSegId(id);
      if (id) {
        setClickLngLat({ lng: e.lngLat.lng, lat: e.lngLat.lat });
        keepClearOfPanel(map, e.point);
      } else {
        setClickLngLat(null);
        setPickedRoad(null);
      }
    };
    const move = (e: maplibregl.MapMouseEvent) => {
      const over = !!queryImported(map, layersRef.current, e.point) || !!roadAt(map, e.point);
      map.getCanvas().style.cursor = over ? "pointer" : "";
    };
    map.on("click", click);
    map.on("mousemove", move);
    return () => {
      map.off("click", click);
      map.off("mousemove", move);
    };
  }, [map]);

  // A different road (or none) is selected: leave design mode.
  useEffect(() => setDesigning(false), [segId]);

  // Load the clicked segment's details.
  useEffect(() => {
    if (!segId || !city) {
      setSeg(null);
      return;
    }
    setSegLoading(true);
    setSegError(null);
    roadsApi
      .segment(city.city_id, segId)
      .then(setSeg)
      .catch((e: Error) => setSegError(e.message))
      .finally(() => setSegLoading(false));
  }, [segId, city, dataVersion]);

  useEffect(() => {
    if (!map) return;
    highlight(map, segId, seg?.segment.display_name ?? pickedRoad?.name ?? null);
  }, [map, segId, seg, pickedRoad]);

  const fit = useCallback(
    (b: Bbox) => map?.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: { top: 60, bottom: 60, left: 60, right: 440 }, maxZoom: 17, duration: 800 }),
    [map],
  );

  const showOnMap = useCallback(
    (lon: number, lat: number) => {
      setPage("map");
      setTimeout(() => {
        map?.resize();
        map?.flyTo({ center: [lon, lat], zoom: 16, duration: 800 });
      }, 50);
    },
    [map],
  );

  const featureLayer = feature ? layers.find((l) => l.layer_id === feature.layerId) : undefined;

  return (
    <div className="flex h-full flex-col font-sans text-slate-800">
      <nav className="flex items-center gap-1 border-b border-slate-200 bg-white px-4">
        <span className="mr-4 py-2 text-base font-semibold">City Planning OS</span>
        <span className="mr-4 text-sm text-slate-500">{city ? `${city.name}, ${city.state}` : "Loading…"}</span>
        {(["map", "inbox", "rules"] as Page[]).map((p) => (
          <button key={p} onClick={() => setPage(p)}
            className={`border-b-2 px-3 py-2 text-sm ${page === p ? "border-blue-600 font-medium text-blue-700" : "border-transparent text-slate-600 hover:text-slate-900"}`}>
            {p === "map" ? "Map" : p === "inbox" ? "Data inbox" : "Rules"}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-4 text-xs text-slate-500">
          {error && <span className="text-red-600">Backend not reachable: {error}</span>}
          {health && (
            <span className="flex items-center gap-1.5" title={`Data: ${health.data_dir}`}>
              <span className={`inline-block h-2 w-2 rounded-full ${health.status === "ok" ? "bg-green-500" : "bg-amber-500"}`} />
              Backend {health.status} · data on this machine
            </span>
          )}
          {system && (
            <span className={system.llm_is_external ? "font-medium text-amber-700" : ""}>
              AI: {system.llm_is_external ? `${system.llm_provider} (external: prompt text leaves this machine)` : `local (${system.llm_model})`}
            </span>
          )}
        </div>
      </nav>

      <div className="min-h-0 flex-1">
        {/* The map stays mounted while on the inbox page, so it keeps its place. */}
        <div className={`h-full ${page === "map" ? "flex" : "hidden"}`}>
          <aside className="flex w-80 shrink-0 flex-col border-r border-slate-200 bg-white">
            {city && layers.some((l) => l.layer_id === "roads") && (
              <div className="border-b border-slate-200 px-4 py-3">
                <RoadSearch cityId={city.city_id} onPick={(hit) => { setSegId(null); setFeature(null); setPickedRoad(hit); fit(hit.bbox); }} />
              </div>
            )}
            <section className="flex-1 overflow-y-auto px-4 py-3">
              <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Layers</h2>
              {topics.map((t) => {
                const topicLayers = layers.filter((l) => l.topic === t.topic);
                return (
                  <div key={t.topic} className="mb-4">
                    <div className="text-sm font-medium">{t.label}</div>
                    {topicLayers.length === 0 && <div className="text-xs text-slate-400">No layers yet</div>}
                    {topicLayers.map((l) => (
                      <div key={l.layer_id} className="mt-1">
                        <label className="flex items-center gap-2 text-sm">
                          <input type="checkbox" checked={visible[l.layer_id] !== false}
                            onChange={(e) => setVisible((v) => ({ ...v, [l.layer_id]: e.target.checked }))} />
                          {l.kind === "imported" && <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: l.color ?? "#475569" }} />}
                          {l.label}
                          {l.has_sample_data && (
                            <span className="rounded bg-orange-100 px-1 text-[10px] font-semibold text-orange-800" title="Contains made-up test data">SAMPLE</span>
                          )}
                          <span className="ml-auto text-xs text-slate-400">{l.feature_count.toLocaleString()}</span>
                        </label>
                        {l.layer_id === "roads" && <WidthLegend />}
                      </div>
                    ))}
                  </div>
                );
              })}
            </section>
          </aside>

          <main className="relative flex-1">
            {city && <CityMap city={city} onMapReady={setMap} />}
            {segId && designing && seg && city && (
              <DesignPanel cityId={city.city_id} segId={segId} roadWidthM={seg.segment.width_m}
                roadWidthSource={seg.segment.width_source} onBack={() => setDesigning(false)}
                onClose={() => { setDesigning(false); setSegId(null); setPickedRoad(null); }} />
            )}
            {segId && !designing && (
              <RoadPanel data={seg} loading={segLoading} error={segError}
                lngLat={clickLngLat ?? undefined}
                onClose={() => { setSegId(null); setPickedRoad(null); setClickLngLat(null); }}
                onZoomToRoad={() => seg?.road && fit(seg.road.bbox)}
                onDesign={() => setDesigning(true)} />
            )}
            {feature && featureLayer && (
              <FeaturePanel layer={featureLayer} layerType={layerTypes.find((t) => t.layer_id === feature.layerId)}
                properties={feature.properties}
                sourceName={featureLayer.sources.find((s) => s.source_id === feature.properties.source_id)?.name}
                onClose={() => setFeature(null)} />
            )}
            {!segId && !feature && pickedRoad && (
              <div className="absolute right-3 top-3 z-10 w-80 rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm shadow-lg">
                <div className="font-semibold">{pickedRoad.name}</div>
                <div className="text-xs text-slate-500">
                  {(pickedRoad.length_m / 1000).toFixed(2)} km in {pickedRoad.segments} segments
                </div>
                <div className="mt-1 text-xs text-slate-600">Click a highlighted segment for its details.</div>
              </div>
            )}
          </main>
        </div>

        {page === "inbox" && city && (
          <InboxPage cityId={city.city_id} topics={topics} system={system} dataDir={health?.data_dir}
            onDataChanged={() => setDataVersion((v) => v + 1)} onShowOnMap={showOnMap} />
        )}
        {page === "rules" && <RulesPage />}
      </div>
    </div>
  );
}

function WidthLegend() {
  return (
    <div className="ml-6 mt-2 space-y-1 text-xs text-slate-600">
      <div className="text-slate-500">Colour = how far to trust the width</div>
      {(Object.keys(CONFIDENCE) as WidthSource[]).map((k) => (
        <div key={k} className="flex items-center gap-2" title={CONFIDENCE[k].help}>
          <span className="inline-block h-1.5 w-5 rounded" style={{ background: CONFIDENCE[k].color }} />
          {CONFIDENCE[k].label}
        </div>
      ))}
    </div>
  );
}
