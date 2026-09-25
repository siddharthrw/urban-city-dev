import { useCallback, useEffect, useState } from "react";
import type { SystemInfo } from "../api";
import { inboxApi, type ImportRecord, type LayerType, type Preview, type SourceFile } from "./api";
import ImportResult from "./ImportResult";
import MappingTable, { mappingProblems, type Mapping } from "./MappingTable";

type Props = {
  cityId: string;
  source: SourceFile;
  layerTypes: LayerType[];
  system: SystemInfo | null;
  onImported: () => void;
  onShowOnMap: (lon: number, lat: number) => void;
};

export default function ImportWizard({ cityId, source, layerTypes, system, onImported, onShowOnMap }: Props) {
  const existing = source.imports[0];
  const existingId = existing?.import_id;
  const [layerId, setLayerId] = useState<string>(existing?.layer_id ?? layerTypes.find((t) => t.topic === source.topic)?.layer_id ?? "");
  const [sheet, setSheet] = useState<string | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mapping, setMapping] = useState<Mapping>({});
  const [notes, setNotes] = useState<string[]>([]);
  const [epsg, setEpsg] = useState("");
  const [record, setRecord] = useState<ImportRecord | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const layerType = layerTypes.find((t) => t.layer_id === layerId);

  // Load the preview (and any previous import) when the file or sheet changes.
  useEffect(() => {
    setError(null);
    setPreview(null);
    setRecord(null);
    if (source.kind === "stored_only") return;
    inboxApi.preview(cityId, source.source_id, sheet).then(setPreview).catch((e: Error) => setError(e.message));
    if (existingId) inboxApi.getImport(cityId, existingId).then(setRecord).catch(() => undefined);
  }, [cityId, source.source_id, source.kind, sheet, existingId]);

  const suggest = useCallback(
    async (useLlm: boolean) => {
      if (!layerId) return;
      setBusy(useLlm ? "Asking the AI…" : "Detecting columns…");
      setError(null);
      try {
        const s = await inboxApi.suggest(cityId, source.source_id, layerId, sheet, useLlm);
        setMapping((prev) => (useLlm ? { ...prev, ...s.mapping } : s.mapping));
        setNotes(s.notes);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(null);
      }
    },
    [cityId, source.source_id, layerId, sheet],
  );

  // Auto-detect as soon as a layer type is chosen; keep a previous import's confirmed mapping.
  useEffect(() => {
    if (!preview || !layerId) return;
    if (record && record.layer_id === layerId) {
      setMapping(Object.fromEntries(Object.entries(record.mapping).map(([f, c]) => [f, { column: c, method: "saved", score: null }])));
    } else {
      suggest(false);
    }
  }, [preview, layerId, record, suggest]);

  const run = async () => {
    setBusy("Importing…");
    setError(null);
    try {
      const flat = Object.fromEntries(Object.entries(mapping).map(([f, m]) => [f, m?.column ?? null]));
      const r = await inboxApi.runImport(cityId, {
        source_id: source.source_id, layer_id: layerId, mapping: flat, sheet,
        options: epsg ? { epsg: Number(epsg) } : {},
      });
      setRecord(r);
      onImported();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  if (source.kind === "stored_only") {
    return (
      <p className="text-sm text-slate-600">
        This file is stored and registered, but automatic import of this type (PDF tables, photos, Word files) is not
        built yet. For now, type the numbers into a CSV or Excel sheet and upload that.
      </p>
    );
  }

  const problems = layerType && preview ? mappingProblems(layerType.fields, mapping, preview.has_geometry) : [];
  const needsEpsg = preview?.has_geometry && !preview.geometry?.crs;

  return (
    <div className="space-y-5">
      <section className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Import as</div>
          <select aria-label="Layer type" value={layerId} onChange={(e) => setLayerId(e.target.value)}
            className="rounded border border-slate-300 px-2 py-1.5 text-sm">
            <option value="">Choose what this file contains…</option>
            {layerTypes.map((t) => (
              <option key={t.layer_id} value={t.layer_id}>{t.label}</option>
            ))}
          </select>
        </label>
        {preview?.sheets && preview.sheets.length > 1 && (
          <label className="text-sm">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Sheet</div>
            <select aria-label="Sheet" value={sheet ?? preview.sheet ?? ""} onChange={(e) => setSheet(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1.5 text-sm">
              {preview.sheets.map((s) => <option key={s}>{s}</option>)}
            </select>
          </label>
        )}
      </section>
      {layerType && <p className="-mt-3 text-xs text-slate-500">{layerType.description}</p>}

      {preview && (
        <section>
          <h3 className="mb-1 text-sm font-semibold">
            Preview <span className="font-normal text-slate-500">
              ({preview.row_count} rows{preview.header_row ? `, header found on row ${preview.header_row}` : ""}
              {preview.geometry ? `, ${Object.entries(preview.geometry.types).map(([k, v]) => `${v} ${k}`).join(", ")}` : ""})
            </span>
          </h3>
          {preview.warnings.map((w) => <p key={w} className="text-xs text-amber-700">{w}</p>)}
          <div className="max-h-56 overflow-auto rounded border border-slate-200">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-slate-50">
                <tr>{Object.keys(preview.rows[0] ?? {}).map((c) => <th key={c} className="px-2 py-1 text-left font-medium">{c === "_row_no" ? "row" : c}</th>)}</tr>
              </thead>
              <tbody>
                {preview.rows.map((r, i) => (
                  <tr key={i} className="border-t border-slate-100">
                    {Object.entries(r).map(([c, v]) => <td key={c} className="whitespace-nowrap px-2 py-1">{v ?? ""}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {preview && layerType && (
        <section>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold">Match columns to fields</h3>
            <div className="flex gap-2">
              <button onClick={() => suggest(false)} disabled={!!busy} className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-50">
                Auto-detect
              </button>
              <button onClick={() => suggest(true)} disabled={!!busy} className="rounded border border-violet-300 px-2 py-1 text-xs text-violet-800 hover:bg-violet-50"
                title="The AI sees only column names and types, never your data">
                Ask AI ({system?.llm_is_external ? `${system.llm_provider}, external` : "local"})
              </button>
            </div>
          </div>
          {system?.llm_is_external && (
            <p className="mb-2 text-xs text-amber-700">
              The AI is an external service: column names (not values) are sent to {system.llm_provider}.
            </p>
          )}
          <MappingTable
            fields={layerType.fields}
            columns={preview.columns}
            mapping={mapping}
            hasGeometry={preview.has_geometry}
            onChange={(f, col) => setMapping((m) => ({ ...m, [f]: col ? { column: col, method: "manual", score: null } : null }))}
          />
          {notes.map((n) => <p key={n} className="mt-1 text-xs text-slate-500">{n}</p>)}
          {needsEpsg && (
            <label className="mt-3 block text-sm">
              This file has no coordinate system. EPSG code:{" "}
              <input value={epsg} onChange={(e) => setEpsg(e.target.value.replace(/\D/g, ""))} placeholder="e.g. 32644"
                className="ml-1 w-28 rounded border border-slate-300 px-2 py-1" aria-label="EPSG code" />
            </label>
          )}
          {problems.map((p) => <p key={p} className="mt-1 text-xs text-red-600">{p}</p>)}
          <button onClick={run} disabled={!!busy || problems.length > 0 || (needsEpsg && !epsg && !mapping.road_name)}
            className="mt-3 rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-slate-300">
            {record ? "Import again" : "Import"}
          </button>
        </section>
      )}

      {busy && <p className="text-sm text-slate-500">{busy}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      {record && (
        <section className="border-t border-slate-200 pt-4">
          <h3 className="mb-3 text-sm font-semibold">Result</h3>
          <ImportResult cityId={cityId} record={record} onChanged={(r) => { setRecord(r); onImported(); }}
            onDeleted={() => { setRecord(null); onImported(); }} onShowOnMap={onShowOnMap} />
        </section>
      )}
    </div>
  );
}
