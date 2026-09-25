// Small display helpers shared across the app.

export function formatValue(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") return Number.isInteger(v) ? v.toLocaleString("en-IN") : String(Math.round(v * 100) / 100);
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

export function formatLength(m: number): string {
  return m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`;
}

export function formatBytes(b: number): string {
  if (b >= 1e6) return `${(b / 1e6).toFixed(1)} MB`;
  if (b >= 1e3) return `${Math.round(b / 1e3)} KB`;
  return `${b} B`;
}

const LINK_METHOD: Record<string, string> = {
  location: "by its location",
  name: "by road name",
  name_fuzzy: "by road name (spelling differs)",
  manual: "by hand",
};

export function linkMethodLabel(method: string): string {
  return LINK_METHOD[method] ?? "";
}

const NAME_MATCH: Record<string, string> = {
  same: "OSM and official names agree",
  similar: "OSM and official names are spelling variants",
  different: "OSM and official names differ",
  osm_only: "Only OSM has a name",
  official_only: "Only the official source has a name",
  none: "No name in either source",
};

export function nameMatchLabel(m: string): string {
  return NAME_MATCH[m] ?? m;
}
