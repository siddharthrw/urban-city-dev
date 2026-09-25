import type { Source } from "./api";

const STYLE: Record<Source["authority"], { label: string; cls: string }> = {
  primary: { label: "Cited", cls: "bg-green-100 text-green-800" },
  superseded: { label: "Superseded — never cited", cls: "bg-red-100 text-red-800" },
  expert: { label: "Expert judgement", cls: "bg-blue-100 text-blue-800" },
  placeholder: { label: "Placeholder — uncited", cls: "bg-slate-200 text-slate-700" },
};

export default function SourceBadge({ source }: { source: Source }) {
  const s = STYLE[source.authority];
  return <span className={`rounded px-2 py-0.5 text-xs font-semibold ${s.cls}`}>{s.label}</span>;
}

export function sourceDescription(source: Source): string {
  if (source.authority === "placeholder") return source.detail ?? "Engineering guess, not from any standard.";
  if (source.authority === "expert") return source.detail ?? "Expert judgement.";
  const bits = [source.doc_title ?? source.doc_id ?? "Unknown document"];
  if (source.clause) bits.push(`clause ${source.clause}`);
  if (source.page) bits.push(`p.${source.page}`);
  return bits.join(", ");
}
