import type { FieldSpec, MappingEntry, Preview } from "./api";

export type Mapping = Record<string, MappingEntry | null>;

const METHOD_BADGE: Record<MappingEntry["method"], { label: string; cls: string; help: string }> = {
  auto: { label: "auto", cls: "bg-slate-100 text-slate-700", help: "Matched from the column header" },
  ai: { label: "AI", cls: "bg-violet-100 text-violet-800", help: "Suggested by the AI from column names only; check it" },
  manual: { label: "you", cls: "bg-blue-100 text-blue-800", help: "Chosen by you" },
  saved: { label: "saved", cls: "bg-green-100 text-green-800", help: "Confirmed in the previous import of this file" },
};

const LOCATION_FIELDS = new Set(["latitude", "longitude", "road_name", "area"]);

type Props = {
  fields: FieldSpec[];
  columns: Preview["columns"];
  mapping: Mapping;
  hasGeometry: boolean;
  onChange: (field: string, column: string | null) => void;
};

export default function MappingTable({ fields, columns, mapping, hasGeometry, onChange }: Props) {
  const own = fields.filter((f) => !LOCATION_FIELDS.has(f.field));
  const loc = fields.filter((f) => LOCATION_FIELDS.has(f.field) && !(hasGeometry && (f.field === "latitude" || f.field === "longitude")));
  const used = new Set(Object.values(mapping).filter(Boolean).map((m) => m!.column));

  const row = (f: FieldSpec) => {
    const m = mapping[f.field];
    return (
      <tr key={f.field} className="border-t border-slate-100">
        <td className="py-1.5 pr-3">
          <span className="font-medium">{f.label ?? f.field}</span>
          {f.required && <span className="ml-1 text-red-600" title="Required">*</span>}
          <div className="text-xs text-slate-400">{f.type}{f.min != null ? `, ≥ ${f.min}` : ""}{f.max != null ? `, ≤ ${f.max}` : ""}</div>
        </td>
        <td className="py-1.5 pr-3">
          <select
            aria-label={`Column for ${f.label ?? f.field}`}
            value={m?.column ?? ""}
            onChange={(e) => onChange(f.field, e.target.value || null)}
            className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
          >
            <option value="">— not in this file —</option>
            {columns.map((c) => (
              <option key={c.name} value={c.name} disabled={used.has(c.name) && m?.column !== c.name}>
                {c.name} ({c.type})
              </option>
            ))}
          </select>
          {m?.ai_suggests && <div className="mt-0.5 text-xs text-violet-700">AI suggests “{m.ai_suggests}”</div>}
        </td>
        <td className="py-1.5">
          {m && (
            <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${METHOD_BADGE[m.method].cls}`} title={METHOD_BADGE[m.method].help}>
              {METHOD_BADGE[m.method].label}
            </span>
          )}
        </td>
      </tr>
    );
  };

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
          <th className="pb-1">Field</th>
          <th className="pb-1">Column in your file</th>
          <th className="pb-1" />
        </tr>
      </thead>
      <tbody>
        {own.map(row)}
        <tr>
          <td colSpan={3} className="pt-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Location {hasGeometry ? "(the file has its own map geometry; a road name is optional)" : "(latitude + longitude, or a road name)"}
          </td>
        </tr>
        {loc.map(row)}
      </tbody>
    </table>
  );
}

/** Rows need a location, and required fields need a column. Returns problems in plain words. */
export function mappingProblems(fields: FieldSpec[], mapping: Mapping, hasGeometry: boolean): string[] {
  const out: string[] = [];
  for (const f of fields) {
    if (f.required && !mapping[f.field]) out.push(`Choose a column for “${f.label ?? f.field}”.`);
  }
  const hasLatLon = !!mapping.latitude && !!mapping.longitude;
  if (!hasGeometry && !hasLatLon && !mapping.road_name) {
    out.push("Rows need a location: choose Latitude + Longitude, or a Road name column.");
  }
  if (!!mapping.latitude !== !!mapping.longitude) out.push("Choose both Latitude and Longitude, or neither.");
  return out;
}
