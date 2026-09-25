import { useCallback, useEffect, useState } from "react";
import DocumentSearch from "./DocumentSearch";
import DocumentsPanel from "./DocumentsPanel";
import ExpertSheetPanel from "./ExpertSheetPanel";
import { rulesApi, type Rule } from "./api";
import RuleDetail from "./RuleDetail";
import SourceBadge from "./SourceBadge";

type Tab = "rules" | "documents" | "expert";

const CATEGORY_LABEL: Record<string, string> = { dimension: "Dimension", conditional: "If / Then" };

export default function RulesPage() {
  const [tab, setTab] = useState<Tab>("rules");
  const [rules, setRules] = useState<Rule[]>([]);
  const [statusFilter, setStatusFilter] = useState<"" | "active" | "proposed">("");
  const [selected, setSelected] = useState<Rule | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    rulesApi.list(statusFilter ? { status: statusFilter } : undefined).then(setRules).catch((e: Error) => setError(e.message));
  }, [statusFilter]);

  useEffect(() => {
    reload();
  }, [reload]);

  const selectRule = (r: Rule) => {
    setSelected(r);
    setTab("rules");
  };

  const proposedCount = rules.filter((r) => r.status === "proposed").length;
  const grouped = rules.reduce<Record<string, Rule[]>>((acc, r) => {
    (acc[r.category] ??= []).push(r);
    return acc;
  }, {});

  return (
    <div className="flex h-full min-h-0">
      <aside className="flex w-80 shrink-0 flex-col border-r border-slate-200 bg-white">
        <nav className="flex border-b border-slate-200">
          {([
            ["rules", "Rules"],
            ["documents", "Documents"],
            ["expert", "Expert sheet"],
          ] as [Tab, string][]).map(([t, label]) => (
            <button key={t} onClick={() => setTab(t)}
              className={`flex-1 px-2 py-2 text-sm ${tab === t ? "border-b-2 border-blue-600 font-medium text-blue-700" : "text-slate-600 hover:text-slate-900"}`}>
              {label}
              {t === "rules" && proposedCount > 0 && (
                <span className="ml-1 rounded-full bg-amber-100 px-1.5 text-xs text-amber-800">{proposedCount}</span>
              )}
            </button>
          ))}
        </nav>

        {tab === "rules" && (
          <>
            <div className="border-b border-slate-200 p-3">
              <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
                className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm">
                <option value="">All statuses</option>
                <option value="active">Active</option>
                <option value="proposed">Proposed (needs review)</option>
              </select>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-3">
              {error && <p className="text-sm text-red-600">{error}</p>}
              {rules.length === 0 && !error && <p className="text-sm text-slate-400">No rules yet.</p>}
              {Object.entries(grouped).map(([category, rs]) => (
                <div key={category} className="mb-4">
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    {CATEGORY_LABEL[category] ?? category}
                  </h3>
                  <ul className="space-y-1">
                    {rs.map((r) => (
                      <li key={r.rule_id}>
                        <button onClick={() => setSelected(r)}
                          className={`w-full rounded px-2 py-1.5 text-left text-sm hover:bg-slate-100 ${selected?.rule_id === r.rule_id ? "bg-blue-50 ring-1 ring-blue-200" : ""}`}>
                          <div className="line-clamp-2">{r.statement}</div>
                          <div className="mt-1"><SourceBadge source={r.source} /></div>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </>
        )}
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto bg-slate-50 p-6">
        {tab === "rules" && (
          selected ? (
            <div className="max-w-2xl">
              <RuleDetail
                rule={selected}
                onChanged={(r) => {
                  setSelected(r);
                  reload();
                }}
              />
            </div>
          ) : (
            <div className="max-w-xl text-sm text-slate-600">
              <h2 className="mb-2 text-lg font-semibold text-slate-800">Rules</h2>
              <p>
                Road design standards turned into data. Every rule shows where it comes from: a cited
                clause of a standards document, the partner's own expert judgement, or a clearly
                labelled placeholder guess used until the real standard arrives.
              </p>
              <p className="mt-2">Pick a rule on the left, or add a document / expert sheet.</p>
            </div>
          )
        )}
        {tab === "documents" && (
          <div className="max-w-3xl space-y-6">
            <DocumentSearch />
            <DocumentsPanel onRulesChanged={reload} onSelectRule={selectRule} />
          </div>
        )}
        {tab === "expert" && (
          <div className="max-w-2xl">
            <ExpertSheetPanel onImported={reload} />
          </div>
        )}
      </main>
    </div>
  );
}
