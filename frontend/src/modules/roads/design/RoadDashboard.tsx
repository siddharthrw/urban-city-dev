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
 * direct link here always shows the current data. */
export default function RoadDashboard({ cityId, segId, optionId, context, rowM, onBack }: Props) {
  const [result, setResult] = useState<DesignResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"today" | "option">("today");

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
    <div className="h-full overflow-y-auto bg-slate-100">
      <div className="sticky top-0 z-10 flex items-center gap-3 border-b border-slate-200 bg-white px-6 py-3 shadow-sm">
        <button onClick={onBack} className="text-sm text-blue-600 hover:underline">← Back to design</button>
        <h1 className="text-base font-semibold">
          Street-level dashboard{result?.segment.name ? `: ${result.segment.name}` : ""}
          {option ? ` — ${option.name}` : ""}
        </h1>
      </div>

      <div className="mx-auto max-w-6xl px-6 py-6">
        {error && <p className="text-sm text-red-600">{error}</p>}
        {!result && !error && <p className="text-sm text-slate-400">Loading…</p>}

        {result && !option && (
          <p className="text-sm text-slate-500">
            This option isn't available at the current width ({result.row_m} m). Go back and re-open it from the design panel.
          </p>
        )}

        {result && option && (
          <div className="grid gap-5 lg:grid-cols-3">
            <section aria-label="Street-level detail" className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm lg:col-span-2">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-700">Street-level detail</h2>
                <div className="inline-flex overflow-hidden rounded-md border border-slate-300 text-xs" role="group" aria-label="Scenario">
                  <button onClick={() => setMode("today")} aria-pressed={mode === "today"}
                    className={`px-3 py-1.5 ${mode === "today" ? "bg-blue-600 font-medium text-white" : "bg-white text-slate-600 hover:bg-slate-50"}`}>
                    Today
                  </button>
                  <button onClick={() => setMode("option")} aria-pressed={mode === "option"}
                    className={`border-l border-slate-300 px-3 py-1.5 ${mode === "option" ? "bg-blue-600 font-medium text-white" : "bg-white text-slate-600 hover:bg-slate-50"}`}>
                    {option.name}
                  </button>
                </div>
              </div>
              <div aria-label="Hero scene">
                <RoadScene3D
                  elements={mode === "today" ? result.current.elements : option.elements}
                  rowCm={result.row_cm}
                  geometry={result.segment.geometry}
                  trafficDensity={mode === "today" ? option.impact.before.vc_ratio : option.impact.after.vc_ratio}
                  label={mode === "today" ? "Today" : option.name}
                />
              </div>
              <h2 className="mb-3 mt-6 text-sm font-semibold text-slate-700">Flow map</h2>
              <div className="grid gap-4 sm:grid-cols-2">
                <RoadFlowMap geometry={result.segment.geometry} vcRatio={option.impact.before.vc_ratio} label="Today" />
                <RoadFlowMap geometry={result.segment.geometry} vcRatio={option.impact.after.vc_ratio} label={option.name} />
              </div>
              <h2 className="mb-3 mt-6 text-sm font-semibold text-slate-700">Cross-section</h2>
              <div className="grid gap-4 sm:grid-cols-2">
                <CrossSection elements={result.current.elements} rowCm={result.row_cm} title="Today" />
                <CrossSection elements={option.elements} rowCm={result.row_cm} title={option.name} />
              </div>
            </section>

            <aside className="space-y-4">
              <section aria-label="Metrics" className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <h2 className="mb-3 text-sm font-semibold text-slate-700">Metrics</h2>
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
        )}
      </div>
    </div>
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
