import { useEffect, useState } from "react";
import CrossSection from "./CrossSection";
import RoadFlowMap from "./RoadFlowMap";
import RoadScene3D from "./RoadScene3D";
import TrafficImpactPanel from "./TrafficImpactPanel";
import { designApi, type DesignResult, type DetailTarget } from "./api";

type Props = DetailTarget & { onBack: () => void };

/** Full-page street-level detail for one design option, reached by clicking "Street-level
 * detail" on its card. Re-runs the same /design call DesignPanel already made (cheap,
 * deterministic engine) rather than threading the whole result through navigation state, so a
 * direct link here always shows the current data. Rendered as a fixed-position overlay (see
 * App.tsx) so it's a true fullscreen view over the map, not a page inside the normal app chrome.
 * The dark "control room" styling is purely cosmetic — every number on it comes straight from
 * `result`/`option`, same data DesignPanel shows, nothing invented for effect. */
export default function RoadDashboard({ cityId, segId, optionId, context, rowM, onBack }: Props) {
  const [result, setResult] = useState<DesignResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"today" | "option">("today");
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setResult(null);
    setError(null);
    designApi.design(cityId, segId, { context, row_m: rowM })
      .then((r) => { if (!cancelled) setResult(r); })
      .catch((e) => { if (!cancelled) setError((e as Error).message); });
    return () => { cancelled = true; };
  }, [cityId, segId, context, rowM]);

  const option = result?.options.find((o) => o.option_id === optionId) ?? null;

  return (
    <div className="flex h-full flex-col bg-slate-950 text-slate-100">
      <header className="flex shrink-0 items-center gap-4 border-b border-cyan-500/20 bg-slate-900/90 px-6 py-3">
        <button onClick={onBack} className="text-sm text-cyan-400 hover:text-cyan-300">← Back to design</button>
        <h1 className="text-sm font-semibold uppercase tracking-widest text-slate-200">
          Street-level dashboard{result?.segment.name ? `: ${result.segment.name}` : ""}
          {option ? ` — ${option.name}` : ""}
        </h1>
        <span className="ml-auto flex items-center gap-2 font-mono text-xs text-cyan-400/80" aria-label="Current time">
          <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-cyan-400" />
          {now.toLocaleTimeString("en-IN", { hour12: false })}
        </span>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        {error && <p className="text-sm text-red-400">{error}</p>}
        {!result && !error && <p className="text-sm text-slate-500">Loading…</p>}

        {result && !option && (
          <p className="text-sm text-slate-400">
            This option isn't available at the current width ({result.row_m} m). Go back and re-open it from the design panel.
          </p>
        )}

        {result && option && (
          <div className="mx-auto max-w-[1600px] space-y-5">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
              <Kpi label="Lanes" value={String(option.metrics.lanes)} />
              <Kpi label="Lane width" value={`${option.metrics.lane_width_m} m`} />
              <Kpi label="Footpath" value={`${option.metrics.footpath_m} m`} accent={option.metrics.footpath_m > 0} />
              <Kpi label="Cycle track" value={option.metrics.has_cycle_track ? "Yes" : "No"} accent={option.metrics.has_cycle_track} />
              <Kpi label="Trees" value={option.metrics.has_trees ? "Yes" : "No"} accent={option.metrics.has_trees} />
              <Kpi label="Bus bay" value={option.metrics.has_bus_bay ? "Yes" : "No"} accent={option.metrics.has_bus_bay} />
              <Kpi label="Median" value={option.metrics.has_median ? "Yes" : "No"} accent={option.metrics.has_median} />
            </div>

            <div className="grid gap-5 lg:grid-cols-3">
              <section aria-label="Street-level detail"
                className="rounded-xl border border-cyan-500/20 bg-slate-900/60 p-4 shadow-[0_0_50px_-20px_rgba(34,211,238,0.5)] lg:col-span-2">
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="text-xs font-semibold uppercase tracking-widest text-cyan-300/80">Live corridor view</h2>
                  <div className="inline-flex overflow-hidden rounded-md border border-cyan-500/30 text-xs" role="group" aria-label="Scenario">
                    <button onClick={() => setMode("today")} aria-pressed={mode === "today"}
                      className={`px-3 py-1.5 transition ${mode === "today" ? "bg-cyan-400 font-semibold text-slate-950" : "bg-transparent text-slate-300 hover:bg-slate-800"}`}>
                      Today
                    </button>
                    <button onClick={() => setMode("option")} aria-pressed={mode === "option"}
                      className={`border-l border-cyan-500/30 px-3 py-1.5 transition ${mode === "option" ? "bg-cyan-400 font-semibold text-slate-950" : "bg-transparent text-slate-300 hover:bg-slate-800"}`}>
                      {option.name}
                    </button>
                  </div>
                </div>
                <div aria-label="Hero scene" className="overflow-hidden rounded-lg ring-1 ring-cyan-500/20">
                  <RoadScene3D
                    elements={mode === "today" ? result.current.elements : option.elements}
                    rowCm={result.row_cm}
                    geometry={result.segment.geometry}
                    trafficDensity={mode === "today" ? option.impact.before.vc_ratio : option.impact.after.vc_ratio}
                    label={mode === "today" ? "Today" : option.name}
                  />
                </div>

                <h2 className="mb-3 mt-6 text-xs font-semibold uppercase tracking-widest text-cyan-300/80">Flow map</h2>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="rounded-lg bg-slate-50 p-2">
                    <RoadFlowMap geometry={result.segment.geometry} elements={result.current.elements} vcRatio={option.impact.before.vc_ratio} label="Today" />
                  </div>
                  <div className="rounded-lg bg-slate-50 p-2">
                    <RoadFlowMap geometry={result.segment.geometry} elements={option.elements} vcRatio={option.impact.after.vc_ratio} label={option.name} />
                  </div>
                </div>

                <h2 className="mb-3 mt-6 text-xs font-semibold uppercase tracking-widest text-cyan-300/80">Cross-section</h2>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="rounded-lg bg-slate-50 p-2">
                    <CrossSection elements={result.current.elements} rowCm={result.row_cm} title="Today" />
                  </div>
                  <div className="rounded-lg bg-slate-50 p-2">
                    <CrossSection elements={option.elements} rowCm={result.row_cm} title={option.name} />
                  </div>
                </div>
              </section>

              <aside className="space-y-4">
                <section aria-label="Metrics"
                  className="rounded-xl border border-cyan-500/20 bg-slate-900/60 p-4 shadow-[0_0_50px_-20px_rgba(34,211,238,0.5)]">
                  <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-cyan-300/80">Metrics</h2>
                  <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                    <Metric label="Lanes" value={String(option.metrics.lanes)} />
                    <Metric label="Lane width" value={`${option.metrics.lane_width_m} m`} />
                    <Metric label="Footpath" value={`${option.metrics.footpath_m} m each side`} />
                    <Metric label="Cycle track" value={option.metrics.has_cycle_track ? "yes" : "no"} />
                    <Metric label="Trees" value={option.metrics.has_trees ? "yes" : "no"} />
                    <Metric label="Bus bays" value={option.metrics.has_bus_bay ? "yes" : "no"} />
                    <Metric label="Median" value={option.metrics.has_median ? "yes" : "no"} />
                  </dl>
                </section>
                <TrafficImpactPanel impact={option.impact} />
              </aside>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-1">
      <dt className="text-slate-500">{label}:</dt>
      <dd className="font-medium text-slate-200">{value}</dd>
    </div>
  );
}

function Kpi({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className={`rounded-lg border px-3 py-2 ${accent ? "border-emerald-400/40 bg-emerald-400/5" : "border-slate-700 bg-slate-900/60"}`}>
      <div className="text-[10px] uppercase tracking-widest text-slate-400">{label}</div>
      <div className={`mt-0.5 text-lg font-semibold ${accent ? "text-emerald-300" : "text-slate-100"}`}>{value}</div>
    </div>
  );
}
