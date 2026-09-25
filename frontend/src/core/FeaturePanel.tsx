import type { LayerInfo } from "./api";
import type { LayerType } from "./inbox/api";
import { formatValue, linkMethodLabel } from "./format";

type Props = {
  layer: LayerInfo;
  layerType: LayerType | undefined;
  properties: Record<string, unknown>;
  sourceName: string | undefined;
  onClose: () => void;
};

// Columns the importer adds; shown in the "linked to" block instead of the field list.
const SYSTEM_COLS = new Set([
  "import_id", "source_id", "city_id", "row_no", "is_sample", "seg_id", "seg_ids",
  "link_method", "road_name_matched", "link_distance_m", "link_note", "latitude", "longitude",
]);

export default function FeaturePanel({ layer, layerType, properties: p, sourceName, onClose }: Props) {
  const labels = Object.fromEntries((layerType?.fields ?? []).map((f) => [f.field, f.label ?? f.field]));
  const entries = Object.entries(p).filter(([k, v]) => !SYSTEM_COLS.has(k) && v !== null && v !== "");
  const segIds = parseList(p.seg_ids);

  return (
    <div className="absolute right-3 top-3 z-10 w-96 max-w-[calc(100%-1.5rem)] rounded-lg border border-slate-200 bg-white shadow-lg">
      <div className="flex items-start justify-between border-b border-slate-200 px-4 py-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="inline-block h-3 w-3 rounded-full" style={{ background: layer.color ?? "#475569" }} />
            <h2 className="text-base font-semibold">{layer.label}</h2>
          </div>
          {p.is_sample === true && (
            <span className="mt-1 inline-block rounded bg-orange-100 px-2 py-0.5 text-xs font-semibold text-orange-800">
              SAMPLE: made-up test data
            </span>
          )}
        </div>
        <button onClick={onClose} className="rounded px-2 text-lg leading-none text-slate-400 hover:bg-slate-100" aria-label="Close">
          ×
        </button>
      </div>
      <div className="space-y-3 px-4 py-3 text-sm">
        <dl className="grid grid-cols-[9rem_1fr] gap-y-1">
          {entries.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-slate-500">{labels[k] ?? k}</dt>
              <dd>{formatValue(v)}</dd>
            </div>
          ))}
        </dl>
        <div className="rounded-md border border-slate-200 p-3 text-xs text-slate-600">
          {segIds.length ? (
            <>
              Linked to <b>{String(p.road_name_matched ?? "an unnamed road")}</b> ({segIds.length} segment
              {segIds.length > 1 ? "s" : ""}) {linkMethodLabel(String(p.link_method ?? ""))}
              {p.link_distance_m != null && `, ${p.link_distance_m} m away`}.
            </>
          ) : (
            <>Not linked to a road.</>
          )}
          {p.link_note ? <div className="mt-1">{String(p.link_note)}</div> : null}
        </div>
        <p className="text-xs text-slate-400">
          From {sourceName ?? String(p.source_id)}, row {String(p.row_no)}.
        </p>
      </div>
    </div>
  );
}

function parseList(v: unknown): string[] {
  if (Array.isArray(v)) return v.map(String);
  if (typeof v === "string" && v.startsWith("[")) {
    try {
      return (JSON.parse(v) as unknown[]).map(String);
    } catch {
      return [];
    }
  }
  return [];
}
