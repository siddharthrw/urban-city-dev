// Typed wrappers for the core backend endpoints. Modules add their own API files.
import type { FeatureCollection } from "geojson";

export type City = {
  city_id: string;
  name: string;
  state: string | null;
  country: string | null;
  center: [number, number];
  zoom: number;
  utm_epsg: number;
};

export type Topic = { topic: string; label: string; description: string };

export type Health = {
  status: "ok" | "degraded";
  version: string;
  data_dir: string;
  data_dir_writable: boolean;
  spatial_ok: boolean;
  duckdb_version?: string;
  free_disk_gb?: number;
};

export type SystemInfo = {
  version: string;
  llm_provider: string;
  llm_model: string;
  llm_is_external: boolean;
};

export type LayerInfo = {
  layer_id: string;
  topic: string;
  label: string;
  geometry_type: string;
  feature_count: number;
  built_at: string;
  id_column: string | null;
  tiles_url: string | null;
  tiles: { minzoom: number; maxzoom: number } | null;
  kind: "built" | "imported";
  color: string | null;
  summary_fields: string[];
  has_sample_data: boolean;
  sources: { source_id: string; name: string; origin: string; licence: string; received_at: string }[];
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function handle<T>(res: Response, url: string): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail || `${url}: HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function getJson<T>(url: string): Promise<T> {
  return handle<T>(await fetch(url), url);
}

export async function sendJson<T>(url: string, method: "POST" | "DELETE", body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return handle<T>(res, url);
}

export async function postForm<T>(url: string, form: FormData): Promise<T> {
  return handle<T>(await fetch(url, { method: "POST", body: form }), url);
}

export const api = {
  health: () => getJson<Health>("/health"),
  system: () => getJson<SystemInfo>("/api/system"),
  cities: () => getJson<City[]>("/api/cities"),
  topics: () => getJson<Topic[]>("/api/topics"),
  layers: (cityId: string) => getJson<LayerInfo[]>(`/api/cities/${cityId}/layers`),
  features: (cityId: string, layerId: string, bbox: [number, number, number, number]) =>
    getJson<FeatureCollection & { truncated: boolean }>(
      `/api/cities/${cityId}/layers/${layerId}/features?bbox=${bbox.map((v) => v.toFixed(5)).join(",")}`,
    ),
};
