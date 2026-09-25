import { useEffect, useState } from "react";
import { rulesApi, type Rule, type RuleDoc } from "./api";
import SourceBadge from "./SourceBadge";

type Props = {
  onRulesChanged: () => void;
  onSelectRule: (rule: Rule) => void;
};

export default function DocumentsPanel({ onRulesChanged, onSelectRule }: Props) {
  const [docs, setDocs] = useState<RuleDoc[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [proposals, setProposals] = useState<Record<string, Rule[]>>({});

  // Upload form state.
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [authority, setAuthority] = useState<"active" | "superseded">("active");
  const [year, setYear] = useState("");
  const [jurisdiction, setJurisdiction] = useState("");
  const [uploading, setUploading] = useState(false);

  const reload = () => rulesApi.documents().then(setDocs).catch((e: Error) => setError(e.message));
  useEffect(() => {
    reload();
  }, []);

  const upload = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await rulesApi.uploadDocument(file, {
        authority, title: title || undefined,
        doc_year: year ? Number(year) : undefined, jurisdiction: jurisdiction || undefined,
      });
      setFile(null);
      setTitle("");
      setYear("");
      setJurisdiction("");
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const embed = async (sourceId: string) => {
    setBusyId(sourceId);
    setError(null);
    try {
      await rulesApi.embedDocument(sourceId);
      await reload();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId(null);
    }
  };

  const extract = async (sourceId: string) => {
    setBusyId(sourceId);
    setError(null);
    try {
      const res = await rulesApi.extractRules(sourceId);
      setProposals((p) => ({ ...p, [sourceId]: res.rules }));
      onRulesChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="mb-3 text-sm font-semibold">Add a standards document (PDF)</h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <label className="col-span-2 text-sm sm:col-span-4">
            <div className="mb-1 text-xs text-slate-500">File</div>
            <input type="file" accept=".pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="block w-full text-sm" />
          </label>
          <label className="col-span-2 text-sm">
            <div className="mb-1 text-xs text-slate-500">Title (optional)</div>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. IRC:103-2012"
              className="w-full rounded border border-slate-300 px-2 py-1.5" />
          </label>
          <label className="text-sm">
            <div className="mb-1 text-xs text-slate-500">Status</div>
            <select value={authority} onChange={(e) => setAuthority(e.target.value as "active" | "superseded")}
              className="w-full rounded border border-slate-300 px-2 py-1.5">
              <option value="active">Active (current standard)</option>
              <option value="superseded">Superseded (replaced; never cited)</option>
            </select>
          </label>
          <label className="text-sm">
            <div className="mb-1 text-xs text-slate-500">Year</div>
            <input value={year} onChange={(e) => setYear(e.target.value.replace(/\D/g, ""))} placeholder="e.g. 2012"
              className="w-full rounded border border-slate-300 px-2 py-1.5" />
          </label>
          <label className="col-span-2 text-sm sm:col-span-4">
            <div className="mb-1 text-xs text-slate-500">Jurisdiction (optional)</div>
            <input value={jurisdiction} onChange={(e) => setJurisdiction(e.target.value)} placeholder="e.g. India, Tamil Nadu, Chennai"
              className="w-full rounded border border-slate-300 px-2 py-1.5" />
          </label>
        </div>
        <button onClick={upload} disabled={!file || uploading}
          className="mt-3 rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-slate-300">
          {uploading ? "Uploading…" : "Upload & ingest"}
        </button>
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      </section>

      <section>
        <h3 className="mb-2 text-sm font-semibold">Ingested documents</h3>
        {docs.length === 0 && <p className="text-sm text-slate-400">None yet.</p>}
        <ul className="space-y-3">
          {docs.map((d) => (
            <li key={d.source_id} className="rounded-lg border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{d.name}</span>
                {d.sample && (
                  <span className="rounded bg-orange-100 px-1.5 py-0.5 text-xs font-semibold text-orange-800">SAMPLE</span>
                )}
                <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${d.authority === "superseded" ? "bg-red-100 text-red-800" : "bg-green-100 text-green-800"}`}>
                  {d.authority ?? "unknown status"}
                </span>
                {d.jurisdiction && <span className="text-xs text-slate-500">{d.jurisdiction}{d.doc_year ? `, ${d.doc_year}` : ""}</span>}
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {d.chunks} chunk{d.chunks === 1 ? "" : "s"} · {d.embedded ? "embedded" : "not embedded yet"} · {d.licence}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <button onClick={() => embed(d.source_id)} disabled={busyId === d.source_id || d.chunks === 0}
                  className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50 disabled:opacity-50">
                  {d.embedded ? "Re-embed" : "Embed"}
                </button>
                <button onClick={() => extract(d.source_id)}
                  disabled={busyId === d.source_id || !d.embedded || d.authority === "superseded"}
                  className="rounded border border-violet-300 px-2 py-1 text-xs text-violet-800 hover:bg-violet-50 disabled:opacity-50"
                  title={d.authority === "superseded" ? "Superseded documents cannot be used to propose rules" : "Ask the AI to propose rules from this document"}>
                  {busyId === d.source_id ? "Working…" : "Extract rules (AI)"}
                </button>
              </div>
              {proposals[d.source_id] && (
                <ul className="mt-3 space-y-1 border-t border-slate-100 pt-2">
                  {proposals[d.source_id].length === 0 && <li className="text-xs text-slate-400">No rules found in this document.</li>}
                  {proposals[d.source_id].map((r) => (
                    <li key={r.rule_id}>
                      <button onClick={() => onSelectRule(r)} className="flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-left text-sm hover:bg-slate-50">
                        <span>{r.statement}</span>
                        <SourceBadge source={r.source} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
