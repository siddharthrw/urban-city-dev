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
 *
 * Layout: the 3D corridor fills the first screen edge-to-edge, with glass readout panels
 * floating over it (not stacked above it) — approved from docs/dashboard_redesign_mockup (the
 * published Artifact). Flow map and cross-section stay reachable below, by scrolling past the
 * hero, rather than disappearing. The dark "control room" styling is purely cosmetic — every
 * number on it comes straight from `result`/`option`, same data DesignPanel shows, nothing
 * invented for effect. */
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
  const impact = option?.impact ?? null;
  const vcRatio = impact ? (mode === "today" ? impact.before.vc_ratio : impact.after.vc_ratio) : null;
  const lanes = impact ? (mode === "today" ? impact.before.lanes : impact.after.lanes) : null;

  return (
    <div className="h-full overflow-y-auto bg-slate-950 text-slate-100">
      {/* ======================= Hero: fullscreen corridor + floating panels ======================= */}
      <section aria-label="Street-level detail" className="relative h-screen w-full">
        {(!result || error || (result && !option)) && (
          <div className="flex h-full items-center justify-center px-6">
            {error && <p className="text-sm text-red-400">{error}</p>}
            {!result && !error && <p className="text-sm text-slate-500">Loading…</p>}
            {result && !option && (
              <p className="text-sm text-slate-400">
                This option isn't available at the current width ({result.row_m} m). Go back and re-open it from the design panel.
              </p>
            )}
          </div>
        )}

        {result && option && impact && (
          <>
            <section aria-label="Hero scene" className="absolute inset-0">
              <RoadScene3D
                elements={mode === "today" ? result.current.elements : option.elements}
                rowCm={result.row_cm}
                geometry={result.segment.geometry}
                trafficDensity={vcRatio}
                label={mode === "today" ? "Today" : option.name}
                hideLabel
                hud={<SceneVignette />}
              />
            </section>

            <header className="absolute inset-x-0 top-0 z-20 flex items-center gap-4 bg-gradient-to-b from-slate-950/85 to-transparent px-5 py-3.5">
              <button onClick={onBack} className="text-sm text-cyan-400 hover:text-cyan-300">← Back to design</button>
              <div className="mx-auto rounded-lg border border-cyan-500/20 bg-slate-950/55 px-4 py-1.5 text-center backdrop-blur-sm">
                <div className="text-xs font-semibold uppercase tracking-widest text-slate-100">
                  {result.segment.name ?? "Street-level dashboard"} — {option.name}
                </div>
              </div>
              <span className="ml-auto flex items-center gap-2 font-mono text-xs text-cyan-200/85" aria-label="Current time">
                <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-cyan-400" />
                {now.toLocaleTimeString("en-IN", { hour12: false })}
              </span>
            </header>

            {/* Floating left column: KPI chips */}
            <div className="absolute left-5 top-[76px] z-20 flex flex-col gap-2">
              <Chip label="Lanes" value={String(option.metrics.lanes)} />
              <Chip label="Footpath" value={`${option.metrics.footpath_m} m`} accent={option.metrics.footpath_m > 0} />
              <Chip label="Cycle track" value={option.metrics.has_cycle_track ? "Yes" : "No"} accent={option.metrics.has_cycle_track} />
              <Chip label="Trees" value={option.metrics.has_trees ? "Yes" : "No"} accent={option.metrics.has_trees} />
            </div>

            {/* Floating right column: scenario toggle, legend, engine badge */}
            <div className="absolute right-5 top-[76px] z-20 flex flex-col items-end gap-2">
              <div className="inline-flex overflow-hidden rounded-lg border border-cyan-500/30 text-xs backdrop-blur-sm" role="group" aria-label="Scenario">
                <button onClick={() => setMode("today")} aria-pressed={mode === "today"}
                  className={`px-3 py-1.5 transition ${mode === "today" ? "bg-cyan-400 font-semibold text-slate-950" : "bg-slate-950/55 text-slate-300 hover:bg-slate-800/70"}`}>
                  Today
                </button>
                <button onClick={() => setMode("option")} aria-pressed={mode === "option"}
                  className={`border-l border-cyan-500/30 px-3 py-1.5 transition ${mode === "option" ? "bg-cyan-400 font-semibold text-slate-950" : "bg-slate-950/55 text-slate-300 hover:bg-slate-800/70"}`}>
                  {option.name}
                </button>
              </div>
              <Legend elements={mode === "today" ? result.current.elements : option.elements} />
              <span className="rounded-lg border border-emerald-500/30 bg-slate-950/55 px-3 py-1 font-mono text-[10px] font-bold uppercase tracking-widest text-emerald-400 backdrop-blur-sm">
                {impact.engine === "sumo" ? "SUMO" : "Sample"}
              </span>
            </div>

            {/* Floating bottom row: metrics, simulated impact, capacity gauge */}
            <div className="absolute inset-x-5 bottom-5 z-20 flex flex-wrap gap-3">
              <section aria-label="Metrics" className="min-w-[220px] flex-1 rounded-xl border border-cyan-500/20 bg-slate-950/60 p-4 backdrop-blur-md">
                <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-cyan-300/80">Metrics</h2>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
                  <Metric label="Lane width" value={`${option.metrics.lane_width_m} m`} />
                  <Metric label="Bus bays" value={option.metrics.has_bus_bay ? "yes" : "no"} />
                  <Metric label="Median" value={option.metrics.has_median ? "yes" : "no"} />
                  <Metric label="Footpath" value={`${option.metrics.footpath_m} m each side`} />
                </dl>
              </section>
              <div className="min-w-[280px] flex-[2] rounded-xl border border-cyan-500/20 bg-slate-950/60 p-1 backdrop-blur-md">
                <TrafficImpactPanel impact={impact} />
              </div>
              <div className="flex min-w-[150px] flex-col items-center justify-center rounded-xl border border-cyan-500/20 bg-slate-950/60 p-4 backdrop-blur-md">
                <CapacityGauge vcRatio={vcRatio} lanes={lanes} />
              </div>
            </div>
          </>
        )}
      </section>

      {/* ======================= Below the fold: flow map + cross-section ======================= */}
      {result && option && (
        <div className="mx-auto max-w-[1600px] px-6 py-8">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-cyan-300/80">Flow map</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-2">
              <RoadFlowMap geometry={result.segment.geometry} elements={result.current.elements} vcRatio={option.impact.before.vc_ratio} label="Today" dark />
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-2">
              <RoadFlowMap geometry={result.segment.geometry} elements={option.elements} vcRatio={option.impact.after.vc_ratio} label={option.name} dark />
            </div>
          </div>

          <h2 className="mb-3 mt-8 text-xs font-semibold uppercase tracking-widest text-cyan-300/80">Cross-section</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-2">
              <CrossSection elements={result.current.elements} rowCm={result.row_cm} title="Today" dark />
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-2">
              <CrossSection elements={option.elements} rowCm={result.row_cm} title={option.name} dark />
            </div>
          </div>
        </div>
      )}
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

function Chip({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className={`min-w-[128px] rounded-lg border px-3.5 py-2 backdrop-blur-sm ${accent ? "border-emerald-400/30 bg-emerald-400/10" : "border-slate-600/40 bg-slate-950/55"}`}>
      <div className="text-[9px] uppercase tracking-widest text-slate-400">{label}</div>
      <div className={`text-lg font-semibold ${accent ? "text-emerald-300" : "text-slate-100"}`}>{value}</div>
    </div>
  );
}

const LEGEND: { kind: string; color: string; label: string }[] = [
  { kind: "lane", color: "#8a3b33", label: "Lane" },
  { kind: "cycle_track", color: "#5f93c9", label: "Cycle track" },
  { kind: "footpath", color: "#d6ccb8", label: "Footpath" },
  { kind: "tree_strip", color: "#3c7a3a", label: "Trees" },
];

function Legend({ elements }: { elements: { kind: string }[] }) {
  const present = new Set(elements.map((e) => e.kind));
  const rows = LEGEND.filter((l) => present.has(l.kind));
  if (!rows.length) return null;
  return (
    <div className="rounded-lg border border-slate-600/40 bg-slate-950/55 px-3.5 py-2.5 backdrop-blur-sm" aria-label="Legend">
      <div className="mb-1.5 text-[9px] uppercase tracking-widest text-slate-400">Legend</div>
      <ul className="flex flex-col gap-1 text-[11px] text-slate-300">
        {rows.map((r) => (
          <li key={r.kind} className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: r.color }} />
            {r.label}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** A faint inset vignette on the 3D view so the floating panels have contrast to sit on — no
 * scan-line or corner readouts here, those are the floating panels themselves now. */
function SceneVignette() {
  return <div className="pointer-events-none absolute inset-0 shadow-[inset_0_0_120px_40px_rgba(2,6,23,0.5)]" />;
}

function CapacityGauge({ vcRatio, lanes }: { vcRatio: number | null; lanes: number | null }) {
  const pct = vcRatio == null ? null : Math.round(Math.min(1, vcRatio) * 100);
  const color = pct == null ? "#64748b" : pct < 50 ? "#34d399" : pct < 80 ? "#fbbf24" : "#f87171";
  const r = 32, c = 2 * Math.PI * r;
  const offset = pct == null ? c : c * (1 - pct / 100);
  return (
    <>
      <svg width="76" height="76" viewBox="0 0 76 76" role="img" aria-label={pct == null ? "No capacity data" : `${pct}% capacity used`}>
        <circle cx="38" cy="38" r={r} fill="none" stroke="rgba(100,116,139,.3)" strokeWidth="8" />
        <circle cx="38" cy="38" r={r} fill="none" stroke={color} strokeWidth="8" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={offset} transform="rotate(-90 38 38)" />
        <text x="38" y="35" textAnchor="middle" fontSize="16" fontWeight="700" fill="#f1f5f9">{pct == null ? "—" : `${pct}%`}</text>
        <text x="38" y="49" textAnchor="middle" fontSize="8" fill="#94a3b8">{lanes ?? "—"} lane{lanes === 1 ? "" : "s"}</text>
      </svg>
      <div className="mt-1 text-[9px] uppercase tracking-widest text-slate-400">Capacity used</div>
    </>
  );
}
