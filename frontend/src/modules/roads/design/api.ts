import { ApiError, sendJson } from "../../../core/api";

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

export type NearbyFeature = {
  type: string;
  flag: string;
  count: number;
  names: string[];
  detail: string;
};

export type DesignResult = {
  row_m: number;
  row_cm: number;
  road_class: string;
  oneway: boolean;
  width_source: "estimated" | "measured" | "verified" | "manual";
  context: string[];
  auto_context: string[];
  nearby: NearbyFeature[];
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

export type ExplainResult = DesignResult & {
  explanations: Record<string, string>;
  comparison: string;
  explanation_warnings: string[];
};

export type ExplainOneResult = {
  explanation: string;
  warnings: string[];
};

export type VerifyWidthResult = {
  seg_id: string;
  width_m: number;
  width_source: "verified";
  width_source_detail: string | null;
};

export const designApi = {
  design: (cityId: string, segId: string, body: { context: string[]; row_m?: number }) =>
    sendJson<DesignResult>(`/api/roads/${cityId}/segments/${encodeURIComponent(segId)}/design`, "POST", body),

  setVerifiedWidth: (cityId: string, segId: string, body: { width_m: number; note?: string }) =>
    sendJson<VerifyWidthResult>(
      `/api/roads/${cityId}/segments/${encodeURIComponent(segId)}/width/verify`,
      "POST",
      body,
    ),

  explain: (cityId: string, segId: string, body: { context: string[]; row_m?: number }) =>
    sendJson<ExplainResult>(
      `/api/roads/${cityId}/segments/${encodeURIComponent(segId)}/design/explain`,
      "POST",
      body,
    ),

  explainOption: (cityId: string, segId: string, optionId: string, body: { context: string[]; row_m?: number }) =>
    sendJson<ExplainOneResult>(
      `/api/roads/${cityId}/segments/${encodeURIComponent(segId)}/design/explain/${encodeURIComponent(optionId)}`,
      "POST",
      body,
    ),

  downloadPdf: (cityId: string, segId: string, params: { row_m?: number; context?: string[] }) => {
    const url = new URL(
      `/api/roads/${cityId}/segments/${encodeURIComponent(segId)}/design/pdf`,
      window.location.href,
    );
    if (params.row_m !== undefined) url.searchParams.set("row_m", String(params.row_m));
    for (const c of params.context ?? []) url.searchParams.append("context", c);
    return fetch(url.toString()).then(async (res) => {
      if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
          const body = await res.json();
          if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
        } catch { /* not JSON */ }
        throw new ApiError(res.status, `PDF export failed: ${detail}`);
      }
      return res.blob();
    });
  },
};
