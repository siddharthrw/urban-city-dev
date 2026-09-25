import { CONFIDENCE } from "../../core/provenance";
import type { SegmentResponse } from "./api";

const km = (m: number) => (m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`);
const CLASS_LABEL: Record<string, string> = {
  motorway: "Motorway", trunk: "Trunk road", primary: "Primary (main road)", secondary: "Secondary",
  tertiary: "Tertiary", unclassified: "Minor road", residential: "Residential street",
  living_street: "Living street",
};

type Props = {
  data: SegmentResponse | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onZoomToRoad: () => void;
};

export default function RoadPanel({ data, loading, error, onClose, onZoomToRoad }: Props) {
  const s = data?.segment;
  const conf = s ? CONFIDENCE[s.width_source] : null;

  return (
    <div className="absolute right-3 top-3 z-10 w-96 max-w-[calc(100%-1.5rem)] rounded-lg border border-slate-200 bg-white shadow-lg">
      <div className="flex items-start justify-between border-b border-slate-200 px-4 py-3">
        <div>
          <h2 className="text-base font-semibold">{s ? s.name ?? "Unnamed road" : "Road"}</h2>
          {s && (
            <p className="text-xs text-slate-500">
              {CLASS_LABEL[s.road_class] ?? s.road_class.replace("_", " ")}
              {s.ref ? ` · ${s.ref}` : ""}
            </p>
          )}
        </div>
        <button onClick={onClose} className="rounded px-2 text-lg leading-none text-slate-400 hover:bg-slate-100" aria-label="Close">
          ×
        </button>
      </div>

      <div className="space-y-3 px-4 py-3 text-sm">
        {loading && <p className="text-slate-400">Loading…</p>}
        {error && <p className="text-red-600">{error}</p>}
        {s && conf && (
          <>
            <dl className="grid grid-cols-[7rem_1fr] gap-y-1">
              <dt className="text-slate-500">This segment</dt>
              <dd>{km(s.length_m)}</dd>
              {data?.road && (
                <>
                  <dt className="text-slate-500">Whole road</dt>
                  <dd>
                    {km(data.road.length_m)} in {data.road.segments} segments{" "}
                    <button onClick={onZoomToRoad} className="text-blue-600 hover:underline">
                      show
                    </button>
                  </dd>
                </>
              )}
              <dt className="text-slate-500">Direction</dt>
              <dd>{s.oneway ? "One-way" : "Two-way"}</dd>
              {s.lanes_osm != null && (
                <>
                  <dt className="text-slate-500">Lanes (OSM)</dt>
                  <dd>{s.lanes_osm}</dd>
                </>
              )}
            </dl>

            <div className="rounded-md border border-slate-200 p-3">
              <div className="flex items-center justify-between">
                <span className="text-slate-500">Width (right-of-way)</span>
                <span className={`rounded px-2 py-0.5 text-xs font-semibold uppercase ${conf.badge}`} title={conf.help}>
                  {conf.label}
                </span>
              </div>
              <div className="mt-1 text-2xl font-semibold">
                {s.width_source === "estimated" ? "~" : ""}
                {s.width_m} m
              </div>
              <p className="mt-1 text-xs text-slate-600">{s.width_source_detail}</p>
              {s.osm_width_hint && (
                <p className="mt-2 text-xs text-slate-500">
                  OSM also has <code>width={s.osm_width_hint}</code>. Shown as a hint only: in OSM this often means
                  the carriageway, not the full right-of-way.
                </p>
              )}
            </div>

            <p className="text-xs text-slate-400">
              Geometry, name and type: {data?.geometry_source?.name} ({data?.geometry_source?.licence}), downloaded{" "}
              {data?.geometry_source?.downloaded}. Segment {s.seg_id}.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
