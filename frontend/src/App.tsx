import { useCallback, useEffect, useState } from "react";
import type * as maplibregl from "maplibre-gl";
import { api, type City, type Health, type LayerInfo, type SystemInfo, type Topic } from "./core/api";
import CityMap from "./core/map/CityMap";
import { CONFIDENCE, type WidthSource } from "./core/provenance";
import { roadsApi, type SearchHit, type SegmentResponse } from "./modules/roads/api";
import { addRoadsLayer, highlight, onRoadClick, setRoadsVisible } from "./modules/roads/roadsLayer";
import RoadPanel from "./modules/roads/RoadPanel";
import RoadSearch from "./modules/roads/RoadSearch";

type Bbox = [number, number, number, number];

export default function App() {
  const [cities, setCities] = useState<City[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [layers, setLayers] = useState<LayerInfo[]>([]);
  const [visible, setVisible] = useState<Record<string, boolean>>({ roads: true });
  const [health, setHealth] = useState<Health | null>(null);
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [map, setMap] = useState<maplibregl.Map | null>(null);

  const [segId, setSegId] = useState<string | null>(null);
  const [seg, setSeg] = useState<SegmentResponse | null>(null);
  const [segLoading, setSegLoading] = useState(false);
  const [segError, setSegError] = useState<string | null>(null);
  const [pickedRoad, setPickedRoad] = useState<SearchHit | null>(null);

  const city = cities[0];

  useEffect(() => {
    Promise.all([api.cities(), api.topics(), api.health(), api.system()])
      .then(([c, t, h, s]) => {
        setCities(c);
        setTopics(t);
        setHealth(h);
        setSystem(s);
        return c[0] ? api.layers(c[0].city_id).then(setLayers) : undefined;
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  // Put the roads layer on the map once both the map and the layer list are ready.
  useEffect(() => {
    const roads = layers.find((l) => l.layer_id === "roads");
    if (!map || !roads) return;
    addRoadsLayer(map, roads);
    return onRoadClick(map, (id) => {
      setSegId(id);
      if (!id) setPickedRoad(null);
    });
  }, [map, layers]);

  useEffect(() => {
    if (map) setRoadsVisible(map, visible.roads !== false);
  }, [map, visible]);

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
  }, [segId, city]);

  useEffect(() => {
    if (!map) return;
    const name = seg?.segment.name ?? pickedRoad?.name ?? null;
    highlight(map, segId, name);
  }, [map, segId, seg, pickedRoad]);

  const fit = useCallback(
    (b: Bbox) => map?.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: { top: 60, bottom: 60, left: 60, right: 440 }, maxZoom: 17, duration: 800 }),
    [map],
  );

  return (
    <div className="flex h-full font-sans text-slate-800">
      <aside className="flex w-80 shrink-0 flex-col border-r border-slate-200 bg-white">
        <header className="border-b border-slate-200 px-4 py-3">
          <h1 className="text-lg font-semibold">City Planning OS</h1>
          <p className="text-sm text-slate-500">{city ? `${city.name}, ${city.state}` : "Loading…"}</p>
        </header>

        {city && layers.some((l) => l.layer_id === "roads") && (
          <div className="border-b border-slate-200 px-4 py-3">
            <RoadSearch
              cityId={city.city_id}
              onPick={(hit) => {
                setSegId(null);
                setPickedRoad(hit);
                fit(hit.bbox);
              }}
            />
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
                      <input
                        type="checkbox"
                        checked={visible[l.layer_id] !== false}
                        onChange={(e) => setVisible((v) => ({ ...v, [l.layer_id]: e.target.checked }))}
                      />
                      {l.label}
                      <span className="ml-auto text-xs text-slate-400">{l.feature_count.toLocaleString()}</span>
                    </label>
                    {l.layer_id === "roads" && <WidthLegend />}
                  </div>
                ))}
              </div>
            );
          })}
        </section>

        <footer className="space-y-1 border-t border-slate-200 px-4 py-2 text-xs text-slate-500">
          {error && <div className="text-red-600">Backend not reachable: {error}</div>}
          {health && (
            <div className="flex items-center gap-2">
              <span className={`inline-block h-2 w-2 rounded-full ${health.status === "ok" ? "bg-green-500" : "bg-amber-500"}`} />
              Backend {health.status} · v{health.version}
            </div>
          )}
          {health && <div title="All data is stored here, on this machine">Data: {health.data_dir}</div>}
          {system && (
            <div className={system.llm_is_external ? "font-medium text-amber-700" : ""}>
              AI: {system.llm_is_external ? `${system.llm_provider} (external; prompt text leaves this machine)` : "local (Ollama)"}
            </div>
          )}
        </footer>
      </aside>

      <main className="relative flex-1">
        {city && <CityMap city={city} onMapReady={setMap} />}
        {segId && (
          <RoadPanel
            data={seg}
            loading={segLoading}
            error={segError}
            onClose={() => {
              setSegId(null);
              setPickedRoad(null);
            }}
            onZoomToRoad={() => seg?.road && fit(seg.road.bbox)}
          />
        )}
        {!segId && pickedRoad && (
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
