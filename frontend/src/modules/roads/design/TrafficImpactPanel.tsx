import type { TrafficImpact } from "./api";

/** Plain-language before/after travel-time readout. Always labelled SAMPLE — see TrafficImpact.note. */
export default function TrafficImpactPanel({ impact }: { impact: TrafficImpact }) {
  const faster = impact.change_pct < 0;
  const arrow = impact.change_pct === 0 ? "→" : faster ? "↓" : "↑";
  return (
    <div className="rounded-md border border-purple-200 bg-purple-50 p-3 text-xs" aria-label="Sample traffic impact">
      <div className="mb-1 flex items-center gap-1.5 font-semibold text-purple-800">
        🚗 Estimated travel-time impact
        <span className="rounded bg-purple-200 px-1.5 py-0.5 text-[10px] font-bold uppercase text-purple-900">SAMPLE</span>
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-purple-900">
        <dt>Today ({impact.before.lanes} lane{impact.before.lanes === 1 ? "" : "s"})</dt>
        <dd>{impact.before.minutes.toFixed(1)} min</dd>
        <dt>This option ({impact.after.lanes} lane{impact.after.lanes === 1 ? "" : "s"})</dt>
        <dd>
          {impact.after.minutes.toFixed(1)} min{" "}
          <span className={faster ? "text-green-700" : impact.change_pct > 0 ? "text-red-700" : "text-purple-700"}>
            ({arrow} {Math.abs(impact.change_pct).toFixed(0)}%)
          </span>
        </dd>
      </dl>
      <p className="mt-1.5 text-purple-700">{impact.note}</p>
      <p className="mt-0.5 text-purple-600">{impact.sample_pcu_detail}</p>
    </div>
  );
}
