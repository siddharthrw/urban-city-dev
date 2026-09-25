import { useState } from "react";
import { inboxApi } from "../inbox/api";
import { rulesApi, type Preview } from "./api";

const FIELD_LABELS: Record<string, string> = {
  if_text: "If", then_text: "Then", because_text: "Because", source_text: "Source",
};

type ImportResult = { imported: number; invalid: number; rule_ids: string[]; problems: { row_no: number; errors: string[] }[] };

export default function ExpertSheetPanel({ onImported }: { onImported: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [sourceId, setSourceId] = useState<string | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [result, setResult] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const upload = async () => {
    if (!file) return;
    setBusy("Uploading…");
    setError(null);
    setResult(null);
    try {
      const { source_id } = await inboxApi.upload("chennai", file, "roads");
      setSourceId(source_id);
      const p = await rulesApi.previewExpertSheet(source_id);
      setPreview(p.preview);
      setMapping(p.mapping);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const doImport = async () => {
    if (!sourceId) return;
    setBusy("Importing…");
    setError(null);
    try {
      const res = await rulesApi.importExpertSheet(sourceId, mapping);
      setResult(res);
      onImported();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const missingRequired = !mapping.if_text || !mapping.then_text;

  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="mb-2 text-sm font-semibold">Expert rules sheet (If / Then / Because / Source)</h3>
        <p className="mb-3 text-xs text-slate-500">
          A CSV or Excel sheet of rules of thumb from experience, one per row. These go straight into
          the active rule set — no AI is involved in reading them, since they're already your own
          structured judgement.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <input type="file" accept=".csv,.xlsx,.xlsm" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-sm" />
          <button onClick={upload} disabled={!file || !!busy}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-slate-300">
            Upload
          </button>
        </div>
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      </section>

      {preview && (
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-2 text-sm font-semibold">
            Match columns <span className="font-normal text-slate-500">({preview.row_count} rows)</span>
          </h3>
          <table className="w-full text-sm">
            <tbody>
              {Object.entries(FIELD_LABELS).map(([field, label]) => (
                <tr key={field} className="border-t border-slate-100">
                  <td className="py-1.5 pr-3 font-medium">
                    {label}
                    {(field === "if_text" || field === "then_text") && <span className="ml-1 text-red-600">*</span>}
                  </td>
                  <td className="py-1.5">
                    <select value={mapping[field] ?? ""} onChange={(e) => setMapping((m) => ({ ...m, [field]: e.target.value }))}
                      className="w-full rounded border border-slate-300 px-2 py-1">
                      <option value="">— not in this file —</option>
                      {preview.columns.map((c) => (
                        <option key={c.name} value={c.name}>{c.name}</option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {missingRequired && <p className="mt-2 text-xs text-red-600">Map at least If and Then.</p>}
          <button onClick={doImport} disabled={!!busy || missingRequired}
            className="mt-3 rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-slate-300">
            Import as rules
          </button>
        </section>
      )}

      {result && (
        <section className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm">
          <p>Imported {result.imported} rule{result.imported === 1 ? "" : "s"}.</p>
          {result.invalid > 0 && (
            <ul className="mt-1 text-xs text-red-700">
              {result.problems.map((p) => (
                <li key={p.row_no}>row {p.row_no}: {p.errors.join("; ")}</li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
