import { getJson, postForm, sendJson } from "../api";

export type Source = {
  authority: "primary" | "superseded" | "expert" | "placeholder";
  doc_id?: string;
  doc_title?: string;
  page?: number;
  clause?: string;
  quote?: string;
  detail?: string;
};

export type Rule = {
  rule_id: string;
  status: "active" | "proposed";
  category: "dimension" | "conditional";
  statement: string;
  element?: string;
  applies_to?: Record<string, string[]>;
  value?: { min_m?: number; max_m?: number };
  condition?: { if: string; then: string; because?: string };
  source: Source;
  file: string | null;
};

export type RuleDoc = {
  source_id: string;
  name: string;
  origin: string;
  licence: string;
  received_at: string;
  authority: "active" | "superseded" | null;
  doc_year: number | null;
  jurisdiction: string | null;
  chunks: number;
  embedded: boolean;
  sample: boolean;
};

export type Hit = { source_id: string; doc_title: string; page: number; text: string; score: number };
export type CheckedHit = Hit & { applies: boolean; reason: string };
export type SearchResult = { found: boolean; message: string | null; best: Hit | null; checked: CheckedHit[] };

export type Preview = {
  columns: { name: string; type: string; filled: number }[];
  rows: Record<string, string | null>[];
  row_count: number;
  header_row: number | null;
  warnings: string[];
};

const base = "/api/rules";

export const rulesApi = {
  list: (params?: { status?: string; category?: string }) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return getJson<Rule[]>(`${base}${q ? `?${q}` : ""}`);
  },
  get: (ruleId: string) => getJson<Rule>(`${base}/${ruleId}`),
  approve: (ruleId: string) => sendJson<Rule>(`${base}/${ruleId}/approve`, "POST"),
  reject: (ruleId: string) => sendJson<{ rejected: string }>(`${base}/${ruleId}/reject`, "POST"),

  documents: () => getJson<RuleDoc[]>(`${base}/documents/list`),
  uploadDocument: (
    file: File,
    fields: { authority: "active" | "superseded"; title?: string; doc_year?: number; jurisdiction?: string },
  ) => {
    const form = new FormData();
    form.append("file", file);
    form.append("authority", fields.authority);
    if (fields.title) form.append("title", fields.title);
    if (fields.doc_year) form.append("doc_year", String(fields.doc_year));
    if (fields.jurisdiction) form.append("jurisdiction", fields.jurisdiction);
    return postForm<{ source_id: string; ingest: { pages: number; pages_with_text: number; chunks: number; chars: number } }>(
      `${base}/documents/upload`,
      form,
    );
  },
  embedDocument: (sourceId: string) =>
    sendJson<{ chunks_embedded: number; dims: number }>(`${base}/documents/${sourceId}/embed`, "POST"),
  extractRules: (sourceId: string, maxChunks?: number) =>
    sendJson<{ stats: { chunks_total: number; chunks_scanned: number; rules_proposed: number }; rules: Rule[] }>(
      `${base}/documents/${sourceId}/extract`,
      "POST",
      { max_chunks: maxChunks ?? null },
    ),
  searchDocuments: (query: string) => sendJson<SearchResult>(`${base}/documents/search`, "POST", { query }),

  previewExpertSheet: (sourceId: string) =>
    getJson<{ preview: Preview; mapping: Record<string, string>; fields: string[] }>(
      `${base}/expert-sheet/${sourceId}/preview`,
    ),
  importExpertSheet: (sourceId: string, mapping: Record<string, string | null>) =>
    sendJson<{ imported: number; invalid: number; rule_ids: string[]; problems: { row_no: number; errors: string[] }[] }>(
      `${base}/expert-sheet/${sourceId}/import`,
      "POST",
      { mapping },
    ),
};
