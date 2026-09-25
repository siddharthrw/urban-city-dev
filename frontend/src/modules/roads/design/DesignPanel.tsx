import { useCallback, useEffect, useState } from "react";
import SourceBadge from "../../../core/rules/SourceBadge";
import { CONFIDENCE } from "../../../core/provenance";
import CrossSection from "./CrossSection";
import { CONTEXT_FLAGS, designApi, type DesignOption, type DesignResult, type ExplainResult } from "./api";

const SOURCE_CHIP: Record<string, string> = {
  data: "bg-green-100 text-green-800",
  default: "bg-slate-200 text-slate-700",
  user: "bg-blue-100 text-blue-800",
  manual: "bg-blue-100 text-blue-800",
  map: "bg-slate-100 text-slate-600",
  estimated: "bg-slate-200 text-slate-700",
  measured: "bg-yellow-100 text-yellow-800",
  verified: "bg-green-100 text-green-800",
};

type Props = {
  cityId: string;
  segId: string;
  roadWidthM: number;
  roadWidthSource: keyof typeof CONFIDENCE;
  onBack: () => void;
  onClose: () => void;
};

export default function DesignPanel({ cityId, segId, roadWidthM, roadWidthSource, onBack, onClose }: Props) {
  const [context, setContext] = useState<string[]>([]);
  const [width, setWidth] = useState(String(roadWidthM));
  const [result, setResult] = useState<DesignResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<ExplainResult | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [explainError, setExplainError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  const run = useCallback(
    async (ctx: string[], widthText: string) => {
      const w = Number(widthText);
      if (!Number.isFinite(w) || w < 3 || w > 150) {
        setError("Width must be a number between 3 and 150 metres.");
        return;
      }
      setLoading(true);
      setError(null);
      setExplanation(null);
      setExplainError(null);
      try {
        setResult(await designApi.design(cityId, segId, { context: ctx, row_m: w }));
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    },
    [cityId, segId],
  );

  const runExplain = useCallback(async () => {
    const w = Number(width);
    setExplaining(true);
    setExplainError(null);
    try {
      setExplanation(await designApi.explain(cityId, segId, { context, row_m: w }));
    } catch (e) {
      setExplainError((e as Error).message);
    } finally {
      setExplaining(false);
    }
  }, [cityId, segId, context, width]);

  const runDownloadPdf = useCallback(async () => {
    const w = Number(width);
    setDownloading(true);
    try {
      const blob = await designApi.downloadPdf(cityId, segId, { row_m: w, context });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `design_${segId}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDownloading(false);
    }
  }, [cityId, segId, context, width]);

  useEffect(() => {
    setWidth(String(roadWidthM));
    setContext([]);
    setExplanation(null);
    setExplainError(null);
    run([], String(roadWidthM));
    // Re-run only when a different road segment is opened.
  }, [segId]);

  const toggle = (id: string) => setContext((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));

  return (
    <div className="absolute right-3 top-3 z-10 flex max-h-[calc(100%-1.5rem)] w-[46rem] max-w-[calc(100%-1.5rem)] flex-col rounded-lg border border-slate-200 bg-white shadow-lg">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
        <div>
          <button onClick={onBack} className="text-xs text-blue-600 hover:underline">← Road details</button>
          <h2 className="text-base font-semibold">Design: {result?.segment.name ?? "unnamed road"}</h2>
        </div>
        <button onClick={onClose} className="rounded px-2 text-lg leading-none text-slate-400 hover:bg-slate-100" aria-label="Close design">×</button>
      </div>

      <div className="space-y-4 overflow-y-auto px-4 py-3 text-sm">
        <section className="rounded-md border border-slate-200 p-3" aria-label="Design inputs">
          <div className="flex flex-wrap items-end gap-4">
            <label className="text-sm">
              <div className="mb-1 text-xs text-slate-500">Right-of-way (m)</div>
              <input value={width} onChange={(e) => setWidth(e.target.value)} inputMode="decimal" aria-label="Right-of-way width in metres"
                className="w-24 rounded border border-slate-300 px-2 py-1.5" />
              <div className="mt-1 text-xs text-slate-500">
                Road's own width: {roadWidthM} m{" "}
                <span className={`rounded px-1.5 py-0.5 font-semibold uppercase ${CONFIDENCE[roadWidthSource].badge}`}>{CONFIDENCE[roadWidthSource].label}</span>
              </div>
            </label>
            <fieldset className="flex flex-wrap gap-x-4 gap-y-1">
              <legend className="mb-1 text-xs text-slate-500">Context</legend>
              {CONTEXT_FLAGS.map((f) => (
                <label key={f.id} className="flex items-center gap-1.5">
                  <input type="checkbox" checked={context.includes(f.id)} onChange={() => toggle(f.id)} />
                  {f.label}
                </label>
              ))}
            </fieldset>
            <button onClick={() => run(context, width)} disabled={loading}
              className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-slate-300">
              {loading ? "Designing…" : "Update design"}
            </button>
            {result && (
              <>
                <button onClick={runExplain} disabled={explaining}
                  aria-label="Explain options"
                  className="rounded border border-blue-300 bg-blue-50 px-3 py-1.5 text-sm text-blue-700 hover:bg-blue-100 disabled:opacity-50">
                  {explaining ? "Explaining…" : "Explain options"}
                </button>
                <button onClick={runDownloadPdf} disabled={downloading}
                  aria-label="Export PDF"
                  className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50">
                  {downloading ? "Generating…" : "Export PDF"}
                </button>
              </>
            )}
          </div>
        </section>

        {error && <p className="text-red-600">{error}</p>}
        {explainError && <p className="text-red-600">{explainError}</p>}

        {result && (
          <>
            {result.warnings.length > 0 && (
              <ul className="space-y-1 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900" aria-label="Warnings">
                {result.warnings.map((w) => <li key={w}>⚠ {w}</li>)}
              </ul>
            )}

            {explanation?.explanation_warnings.map((w) => (
              <p key={w} className="text-xs text-amber-800">⚠ {w}</p>
            ))}

            {explanation?.comparison && (
              <section className="rounded-md border border-blue-100 bg-blue-50 p-3 text-sm text-blue-900" aria-label="AI recommendation">
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-blue-600">AI Recommendation</p>
                <p>{explanation.comparison}</p>
              </section>
            )}

            <details className="text-xs">
              <summary className="cursor-pointer font-medium text-slate-700">What this design used ({result.inputs.length} inputs)</summary>
              <ul className="mt-2 space-y-1">
                {result.inputs.map((i) => (
                  <li key={i.name} className="flex flex-wrap items-baseline gap-2">
                    <span className="w-28 shrink-0 text-slate-500">{i.name}</span>
                    <span className="font-medium">{i.value}</span>
                    <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${SOURCE_CHIP[i.source] ?? "bg-slate-100"}`}>{i.source}</span>
                    <span className="text-slate-500">{i.detail}</span>
                  </li>
                ))}
              </ul>
            </details>

            {result.options.map((o) => (
              <OptionCard key={o.option_id} option={o} result={result}
                explanation={explanation?.explanations[o.option_id] ?? null} />
            ))}

            {result.dropped.length > 0 && (
              <section aria-label="Dropped options">
                <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Not possible at this width</h3>
                <ul className="space-y-1">
                  {result.dropped.map((d) => (
                    <li key={d.option_id} className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs">
                      <b>{d.name}:</b> {d.reason}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
        {!result && loading && <p className="text-slate-400">Designing…</p>}
      </div>
    </div>
  );
}

function OptionCard({ option: o, result, explanation }: { option: DesignOption; result: DesignResult; explanation: string | null }) {
  const m = o.metrics;
  return (
    <section className="rounded-lg border border-slate-200 p-3" aria-label={o.name}>
      <h3 className="text-sm font-semibold">{o.name}</h3>
      <p className="mb-2 text-xs text-slate-600">{o.summary}</p>
      {explanation && (
        <p className="mb-2 text-xs text-blue-800" aria-label={`AI explanation for ${o.name}`}>{explanation}</p>
      )}
      <CrossSection elements={o.elements} rowCm={result.row_cm} title={o.name} />
      <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs">
        <Metric label="Lanes" value={String(m.lanes)} />
        <Metric label="Lane width" value={`${m.lane_width_m} m`} />
        <Metric label="Footpath" value={`${m.footpath_m} m each side`} />
        <Metric label="Cycle track" value={m.has_cycle_track ? "yes" : "no"} />
        <Metric label="Trees" value={m.has_trees ? "yes" : "no"} />
        <Metric label="Bus bays" value={m.has_bus_bay ? "yes" : "no"} />
        <Metric label="Median" value={m.has_median ? "yes" : "no"} />
      </dl>
      {(o.notes.length > 0 || o.omitted.length > 0) && (
        <ul className="mt-2 space-y-0.5 text-xs text-slate-600">
          {o.omitted.map((x) => <li key={x.kind}>– {x.reason}</li>)}
          {o.notes.map((n) => <li key={n}>• {n}</li>)}
        </ul>
      )}
      <details className="mt-2 text-xs">
        <summary className="cursor-pointer text-slate-700">Rules applied ({o.rule_ids.length})</summary>
        <ul className="mt-1 space-y-1">
          {o.rule_ids.map((id) => {
            const r = result.rules[id];
            return (
              <li key={id} className="rounded bg-slate-50 px-2 py-1">
                <span className="mr-2 font-mono text-[11px] text-slate-500">{id}</span>
                <SourceBadge source={{ authority: r.authority }} />
                <div className="mt-0.5">{r.statement}</div>
                <div className="text-slate-500">{r.source}</div>
              </li>
            );
          })}
          {o.uses_fallback_minimums && <li className="text-amber-800">Some elements had no rule; an UNCITED default minimum was used.</li>}
        </ul>
      </details>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-1">
      <dt className="text-slate-500">{label}:</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}
