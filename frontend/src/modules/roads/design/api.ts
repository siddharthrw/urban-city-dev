import { sendJson } from "../../../core/api";

export type ElementKind = "footpath" | "tree_strip" | "cycle_track" | "bus_bay" | "lane" | "median";

export type DesignElement = {
  kind: ElementKind;
  label: string;
  side: "left" | "right" | "centre";
  width_cm: number;
  width_m: number;
  rule_ids: string[];
  fallback_minimum: boolean;
};

export type DesignOption = {
  option_id: string;
  name: string;
  summary: string;
  elements: DesignElement[];
  omitted: { kind: ElementKind; reason: string }[];
  notes: string[];
  metrics: {
    lanes: number;
    carriageway_m: number;
    lane_width_m: number;
    footpath_m: number;
    has_cycle_track: boolean;
    has_trees: boolean;
    has_bus_bay: boolean;
    has_median: boolean;
  };
  rule_ids: string[];
  total_cm: number;
  uses_fallback_minimums: boolean;
};

export type DesignInput = { name: string; value: string; source: string; detail: string };

export type DesignResult = {
  row_m: number;
  row_cm: number;
  road_class: string;
  oneway: boolean;
  width_source: "estimated" | "measured" | "verified" | "manual";
  context: string[];
  inputs: DesignInput[];
  options: DesignOption[];
  dropped: { option_id: string; name: string; reason: string }[];
  warnings: string[];
  rules: Record<string, { statement: string; authority: "primary" | "expert" | "placeholder" | "superseded"; source: string; quote: string | null; page: number | null }>;
  segment: { seg_id: string; name: string | null; road_width_m: number; road_width_source: string };
};

export const CONTEXT_FLAGS: { id: string; label: string }[] = [
  { id: "school_nearby", label: "School nearby" },
  { id: "bus_route", label: "Bus route" },
  { id: "metro_nearby", label: "Metro station nearby" },
  { id: "waterlogging", label: "Waterlogging" },
  { id: "market", label: "Market / shops" },
];

export const designApi = {
  design: (cityId: string, segId: string, body: { context: string[]; row_m?: number }) =>
    sendJson<DesignResult>(`/api/roads/${cityId}/segments/${encodeURIComponent(segId)}/design`, "POST", body),
};
