import { formatLength, formatValue, nameMatchLabel } from "../../core/format";
import { CONFIDENCE } from "../../core/provenance";
import type { SegmentResponse } from "./api";

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
  onDesign?: () => void;
};

export default function RoadPanel({ data, loading, error, onClose, onZoomToRoad, onDesign }: Props) {
  const s = data?.segment;
  const conf = s ? CONFIDENCE[s.width_source] : null;
  const officialLabel = data?.official_name_source?.name ?? "Official";

  return (
    <div className="absolute right-3 top-3 z-10 max-h-[calc(100%-1.5rem)] w-96 max-w-[calc(100%-1.5rem)] overflow-y-auto rounded-lg border border-slate-200 bg-white shadow-lg">
      <div className="flex items-start justify-between border-b border-slate-200 px-4 py-3">
        <div>
          <h2 className="text-base font-semibold">{s ? s.display_name ?? "Unnamed road" : "Road"}</h2>
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
            {(s.name || s.name_official) && (
              <dl className="grid grid-cols-[7rem_1fr] gap-y-1" aria-label="Names">
                <dt className="text-slate-500">OSM name</dt>
                <dd>{s.name ?? <span className="text-slate-400">none</span>}</dd>
                <dt className="text-slate-500">{officialLabel}</dt>
                <dd>{s.name_official ?? <span className="text-slate-400">none</span>}</dd>
                <dd className="col-span-2 text-xs text-slate-400">{nameMatchLabel(s.name_match)}</dd>
              </dl>
            )}

            <dl className="grid grid-cols-[7rem_1fr] gap-y-1">
              <dt className="text-slate-500">This segment</dt>
              <dd>{formatLength(s.length_m)}</dd>
              {data?.road && (
                <>
                  <dt className="text-slate-500">Whole road</dt>
                  <dd>
                    {formatLength(data.road.length_m)} in {data.road.segments} segments{" "}
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

            {onDesign && (
              <button onClick={onDesign}
                className="w-full rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700">
                Design this road
              </button>
            )}

            {data!.linked_data.length > 0 && (
              <div className="space-y-2" aria-label="Linked data">
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Data linked to this road</div>
                {data!.linked_data.map((d) => (
                  <div key={d.layer_id} className="rounded-md border border-slate-200 p-2">
                    <div className="mb-1 flex items-center gap-2 text-sm font-medium">
                      <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: d.color ?? "#475569" }} />
                      {d.label} <span className="text-xs text-slate-400">({d.rows.length})</span>
                    </div>
                    <ul className="space-y-1 text-xs">
                      {d.rows.map((r) => (
                        <li key={`${r.import_id}-${r.row_no}`} className="text-slate-700">
                          {r.is_sample === true && (
                            <span className="mr-1 rounded bg-orange-100 px-1 font-semibold text-orange-800">SAMPLE</span>
                          )}
                          {d.summary_fields
                            .filter((f) => r[f.field] != null)
                            .map((f) => `${f.label}: ${formatValue(r[f.field])}`)
                            .join(" · ")}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}

            <p className="text-xs text-slate-400">
              Geometry and type: {data?.geometry_source?.name} ({data?.geometry_source?.licence}), downloaded{" "}
              {data?.geometry_source?.downloaded}.
              {data?.official_name_source &&
                ` Official name: ${data.official_name_source.name} (${data.official_name_source.licence}).`}{" "}
              Segment {s.seg_id}.
            </p>
          </>
        )}
      </div>
    </div>
  );
}
