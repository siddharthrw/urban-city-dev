import type { TrafficImpact } from "./api";

/** Plain-language before/after travel-time readout. `engine === "sumo"` means this came from a
 * real SUMO microsimulation (see backend/requirements-sumo.txt + simulate.py) — badged distinctly
 * from the BPR-formula estimate, since that's a real difference the viewer should notice. The
 * demand behind either one is still sample data — see TrafficImpact.note. */
export default function TrafficImpactPanel({ impact }: { impact: TrafficImpact }) {
  const faster = impact.change_pct < 0;
  const arrow = impact.change_pct === 0 ? "→" : faster ? "↓" : "↑";
  const sumo = impact.engine === "sumo";
  return (
    <div className={`rounded-md border p-3 text-xs ${sumo ? "border-emerald-200 bg-emerald-50" : "border-purple-200 bg-purple-50"}`}
      aria-label={sumo ? "SUMO-simulated traffic impact" : "Sample traffic impact"}>
      <div className={`mb-1 flex items-center gap-1.5 font-semibold ${sumo ? "text-emerald-800" : "text-purple-800"}`}>
        🚗 {sumo ? "Simulated travel-time impact" : "Estimated travel-time impact"}
        {sumo ? (
          <span className="rounded bg-emerald-200 px-1.5 py-0.5 text-[10px] font-bold uppercase text-emerald-900">SUMO simulation</span>
        ) : (
          <span className="rounded bg-purple-200 px-1.5 py-0.5 text-[10px] font-bold uppercase text-purple-900">SAMPLE</span>
        )}
      </div>
      <dl className={`grid grid-cols-2 gap-x-4 gap-y-0.5 ${sumo ? "text-emerald-900" : "text-purple-900"}`}>
        <dt>Today ({impact.before.lanes} lane{impact.before.lanes === 1 ? "" : "s"})</dt>
        <dd>{impact.before.minutes.toFixed(1)} min</dd>
        <dt>This option ({impact.after.lanes} lane{impact.after.lanes === 1 ? "" : "s"})</dt>
        <dd>
          {impact.after.minutes.toFixed(1)} min{" "}
          <span className={faster ? "text-green-700" : impact.change_pct > 0 ? "text-red-700" : sumo ? "text-emerald-700" : "text-purple-700"}>
            ({arrow} {Math.abs(impact.change_pct).toFixed(0)}%)
          </span>
        </dd>
      </dl>
      <p className={`mt-1.5 ${sumo ? "text-emerald-700" : "text-purple-700"}`}>{impact.note}</p>
      <p className={`mt-0.5 ${sumo ? "text-emerald-600" : "text-purple-600"}`}>{impact.sample_pcu_detail}</p>
    </div>
  );
}
