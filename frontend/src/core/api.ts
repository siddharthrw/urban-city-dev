// Typed wrappers for the core backend endpoints. Modules add their own API files.

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
  llm_is_external: boolean;
};

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: () => getJson<Health>("/health"),
  system: () => getJson<SystemInfo>("/api/system"),
  cities: () => getJson<City[]>("/api/cities"),
  topics: () => getJson<Topic[]>("/api/topics"),
};
