import { getJson, postForm, sendJson } from "../api";

export type FieldSpec = {
  field: string;
  label?: string;
  type: "string" | "int" | "float" | "date";
  required?: boolean;
  description?: string;
  min?: number;
  max?: number;
};

export type LayerType = {
  layer_id: string;
  topic: string;
  label: string;
  description: string;
  color: string | null;
  effects: string[];
  fields: FieldSpec[];
};

export type ImportSummary = {
  import_id: string;
  layer_id: string;
  status: string;
  stats: ImportStats;
  updated_at: string;
};

export type SourceFile = {
  source_id: string;
  name: string;
  topic: string;
  path: string;
  origin: string;
  licence: string;
  received_at: string;
  bytes: number;
  kind: "table" | "gis" | "stored_only" | "unknown";
  sample: boolean;
  system: boolean;
  imports: ImportSummary[];
};

export type UnregisteredFile = { path: string; name: string; topic: string; bytes: number; sample: boolean };

export type Preview = {
  columns: { name: string; type: string; filled: number }[];
  rows: Record<string, string | null>[];
  row_count: number;
  has_geometry: boolean;
  geometry: { types: Record<string, number>; crs: string | null; empty: number } | null;
  sheets: string[] | null;
  sheet: string | null;
  header_row: number | null;
  warnings: string[];
};

export type MappingEntry = { column: string; method: "auto" | "ai" | "manual" | "saved"; score: number | null; ai_suggests?: string };

export type Suggestion = {
  mapping: Record<string, MappingEntry>;
  notes: string[];
  llm: { provider: string; model: string; external: boolean };
};

export type Street = { road_name: string | null; seg_ids: string[]; length_m: number; lon: number; lat: number; score?: number };

export type UnmatchedRow = {
  row_no: number;
  road_name: string | null;
  reason: string | null;
  candidates: Street[];
  has_location: boolean;
};

export type ImportStats = {
  rows_in_file: number;
  imported: number;
  invalid: number;
  linked: number;
  unmatched: number;
  on_map: number;
  by_link_method: Record<string, number>;
  is_sample: boolean;
  warnings: string[];
  effects?: { verified_segments?: number; roads_widths?: Record<string, number> };
};

export type ImportRecord = {
  import_id: string;
  city_id: string;
  source_id: string;
  layer_id: string;
  sheet: string | null;
  mapping: Record<string, string>;
  options: Record<string, unknown>;
  status: string;
  stats: ImportStats;
  problems: { invalid: { row_no: number; errors: string[] }[]; unmatched: UnmatchedRow[] };
};

const base = (city: string) => `/api/inbox/${city}`;

export const inboxApi = {
  layerTypes: () => getJson<LayerType[]>("/api/inbox/layer-types"),
  files: (city: string) => getJson<{ sources: SourceFile[]; unregistered: UnregisteredFile[] }>(`${base(city)}/files`),
  upload: (city: string, file: File, topic: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("topic", topic);
    return postForm<{ source_id: string }>(`${base(city)}/upload`, form);
  },
  register: (city: string, path: string) => sendJson<{ source_id: string }>(`${base(city)}/register`, "POST", { path }),
  preview: (city: string, sourceId: string, sheet?: string | null) =>
    getJson<Preview>(`${base(city)}/sources/${sourceId}/preview${sheet ? `?sheet=${encodeURIComponent(sheet)}` : ""}`),
  suggest: (city: string, sourceId: string, layerId: string, sheet: string | null, useLlm: boolean) =>
    sendJson<Suggestion>(`${base(city)}/sources/${sourceId}/suggest`, "POST", { layer_id: layerId, sheet, use_llm: useLlm }),
  runImport: (city: string, body: { source_id: string; layer_id: string; mapping: Record<string, string | null>; sheet: string | null; options: Record<string, unknown> }) =>
    sendJson<ImportRecord>(`${base(city)}/imports`, "POST", body),
  getImport: (city: string, importId: string) => getJson<ImportRecord>(`${base(city)}/imports/${importId}`),
  linkRow: (city: string, importId: string, rowNo: number, street: Street | null) =>
    sendJson<ImportRecord>(`${base(city)}/imports/${importId}/links`, "POST", {
      row_no: rowNo,
      seg_ids: street?.seg_ids ?? [],
      road_name: street?.road_name ?? null,
    }),
  deleteImport: (city: string, importId: string) => sendJson<{ deleted: string }>(`${base(city)}/imports/${importId}`, "DELETE"),
  streets: (city: string, name: string) =>
    getJson<{ status: string; note: string | null; streets: Street[] }>(`/api/roads/${city}/streets?name=${encodeURIComponent(name)}`),
};
