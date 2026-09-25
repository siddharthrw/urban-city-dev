import { useState } from "react";
import { rulesApi, type Rule } from "./api";
import SourceBadge, { sourceDescription } from "./SourceBadge";

const ELEMENT_LABEL: Record<string, string> = {
  footpath: "Footpath", cycle_track: "Cycle track", tree_strip: "Tree strip", median: "Median",
  bus_bay: "Bus bay", lane: "Lane", verge: "Verge", crossing: "Crossing",
};

type Props = {
  rule: Rule;
  onChanged: (rule: Rule | null) => void;
};

export default function RuleDetail({ rule, onChanged }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const approve = async () => {
    setBusy(true);
    setError(null);
    try {
      onChanged(await rulesApi.approve(rule.rule_id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const reject = async () => {
    if (!confirm(`Reject this proposed rule? It will be deleted (the source document is unaffected).`)) return;
    setBusy(true);
    setError(null);
    try {
      await rulesApi.reject(rule.rule_id);
      onChanged(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-5">
      <header className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-slate-500">
            {rule.element ? ELEMENT_LABEL[rule.element] ?? rule.element : "Conditional rule"}
            <span className="rounded bg-slate-100 px-1.5 py-0.5">{rule.status}</span>
          </div>
          <h2 className="mt-1 text-base font-semibold">{rule.statement}</h2>
        </div>
        <SourceBadge source={rule.source} />
      </header>

      {rule.category === "dimension" && rule.value && (
        <dl className="grid grid-cols-[8rem_1fr] gap-y-1 text-sm">
          {rule.value.min_m != null && (
            <>
              <dt className="text-slate-500">Minimum</dt>
              <dd>{rule.value.min_m} m</dd>
            </>
          )}
          {rule.value.max_m != null && (
            <>
              <dt className="text-slate-500">Maximum</dt>
              <dd>{rule.value.max_m} m</dd>
            </>
          )}
        </dl>
      )}

      {rule.category === "conditional" && rule.condition && (
        <dl className="grid grid-cols-[8rem_1fr] gap-y-1 text-sm">
          <dt className="text-slate-500">If</dt>
          <dd>{rule.condition.if}</dd>
          <dt className="text-slate-500">Then</dt>
          <dd>{rule.condition.then}</dd>
          {rule.condition.because && (
            <>
              <dt className="text-slate-500">Because</dt>
              <dd>{rule.condition.because}</dd>
            </>
          )}
        </dl>
      )}

      {rule.applies_to && Object.keys(rule.applies_to).length > 0 && (
        <p className="text-xs text-slate-500">
          Applies to: {Object.entries(rule.applies_to).map(([k, v]) => `${k}: ${v.join(", ")}`).join("; ")}
        </p>
      )}

      <div className="rounded-md border border-slate-200 p-3 text-sm">
        <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Source</div>
        <p>{sourceDescription(rule.source)}</p>
        {rule.source.quote && (
          <blockquote className="mt-2 border-l-2 border-slate-300 pl-3 text-sm italic text-slate-600">
            “{rule.source.quote}”
          </blockquote>
        )}
      </div>

      {rule.status === "proposed" && (
        <div className="flex items-center gap-2 border-t border-slate-200 pt-3">
          <button onClick={approve} disabled={busy}
            className="rounded bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:bg-slate-300">
            Approve → active
          </button>
          <button onClick={reject} disabled={busy}
            className="rounded border border-red-300 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50">
            Reject
          </button>
          {error && <span className="text-sm text-red-600">{error}</span>}
        </div>
      )}
      {rule.status === "active" && rule.file && (
        <p className="text-xs text-slate-400">Stored in <code>rules/{rule.file}</code>.</p>
      )}
    </div>
  );
}
