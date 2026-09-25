import { useState } from "react";
import { rulesApi, type SearchResult } from "./api";

export default function DocumentSearch() {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<SearchResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    if (!q.trim()) return;
    setBusy(true);
    setError(null);
    setRes(null);
    try {
      setRes(await rulesApi.searchDocuments(q.trim()));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="mb-2 text-sm font-semibold">Ask the ingested documents a question</h3>
      <p className="mb-3 text-xs text-slate-500">
        Finds the passage that best answers your question, then checks with the AI whether it
        actually applies before showing it — so you never get a plausible-looking wrong citation.
      </p>
      <div className="flex gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && run()}
          placeholder="e.g. What is the minimum footpath width?"
          className="flex-1 rounded border border-slate-300 px-2 py-1.5 text-sm" />
        <button onClick={run} disabled={busy || !q.trim()}
          className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-slate-300">
          {busy ? "Checking…" : "Ask"}
        </button>
      </div>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      {res && !res.found && (
        <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-900">{res.message}</p>
      )}
      {res?.best && (
        <div className="mt-3 rounded-md border border-green-200 bg-green-50 p-3 text-sm">
          <div className="text-xs font-semibold uppercase tracking-wide text-green-800">
            {res.best.doc_title}, p.{res.best.page}
          </div>
          <blockquote className="mt-1 italic text-slate-700">“{res.best.text}”</blockquote>
        </div>
      )}
      {res && res.checked.length > 0 && (
        <details className="mt-2 text-xs text-slate-500">
          <summary className="cursor-pointer">All {res.checked.length} candidate passage(s) checked</summary>
          <ul className="mt-1 space-y-1">
            {res.checked.map((c, i) => (
              <li key={i}>
                {c.applies ? "✓" : "✗"} {c.doc_title} p.{c.page} — {c.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
