import { getJson } from "../../core/api";
import type { WidthSource } from "../../core/provenance";

export type Segment = {
  city_id: string;
  seg_id: string;
  osm_way_ids: number[];
  name: string | null;
  name_official: string | null;
  official_road_id: string | null;
  name_match: string;
  display_name: string | null;
  display_name_source: "osm" | "official" | null;
  ref: string | null;
  road_class: string;
  oneway: boolean;
  lanes_osm: number | null;
  osm_width_hint: string | null;
  sidewalk_osm: string | null;
  length_m: number;
  width_m: number;
  width_source: WidthSource;
  width_source_detail: string;
  bbox: [number, number, number, number];
};

export type LinkedData = {
  layer_id: string;
  label: string;
  color: string | null;
  summary_fields: { field: string; label: string }[];
  rows: Record<string, unknown>[];
};

export type SegmentResponse = {
  segment: Segment;
  road: { name: string; segments: number; length_m: number; bbox: [number, number, number, number] } | null;
  geometry_source: { name: string; licence: string; downloaded: string } | null;
  official_name_source: { name: string; licence: string; received: string } | null;
  linked_data: LinkedData[];
};

export type SearchHit = {
  name: string;
  segments: number;
  length_m: number;
  road_class: string;
  bbox: [number, number, number, number];
};

export const roadsApi = {
  segment: (cityId: string, segId: string) =>
    getJson<SegmentResponse>(`/api/roads/${cityId}/segments/${encodeURIComponent(segId)}`),
  search: (cityId: string, q: string) =>
    getJson<SearchHit[]>(`/api/roads/${cityId}/search?q=${encodeURIComponent(q)}`),
};
