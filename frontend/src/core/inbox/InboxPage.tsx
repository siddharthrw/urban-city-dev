import { useCallback, useEffect, useState } from "react";
import type { SystemInfo, Topic } from "../api";
import { formatBytes } from "../format";
import { inboxApi, type LayerType, type SourceFile, type UnregisteredFile } from "./api";
import ImportWizard from "./ImportWizard";

type Props = {
  cityId: string;
  topics: Topic[];
  system: SystemInfo | null;
  dataDir: string | undefined;
  onDataChanged: () => void;
  onShowOnMap: (lon: number, lat: number) => void;
};

export default function InboxPage({ cityId, topics, system, dataDir, onDataChanged, onShowOnMap }: Props) {
  const [sources, setSources] = useState<SourceFile[]>([]);
  const [unregistered, setUnregistered] = useState<UnregisteredFile[]>([]);
  const [layerTypes, setLayerTypes] = useState<LayerType[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [showSystem, setShowSystem] = useState(false);
  const [uploadTopic, setUploadTopic] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const r = await inboxApi.files(cityId);
    setSources(r.sources);
    setUnregistered(r.unregistered);
  }, [cityId]);

  useEffect(() => {
    reload().catch((e: Error) => setError(e.message));
    inboxApi.layerTypes().then(setLayerTypes).catch((e: Error) => setError(e.message));
  }, [reload]);

  const upload = async () => {
    if (!file || !uploadTopic) return;
    setBusy(true);
    setError(null);
    try {
      const { source_id } = await inboxApi.upload(cityId, file, uploadTopic);
      await reload();
      setSelected(source_id);
      setFile(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const register = async (path: string) => {
    setBusy(true);
    try {
      const { source_id } = await inboxApi.register(cityId, path);
      await reload();
      setSelected(source_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const visible = sources.filter((s) => showSystem || !s.system);
  const current = sources.find((s) => s.source_id === selected);

  return (
    <div className="flex h-full min-h-0">
      <aside className="flex w-96 shrink-0 flex-col border-r border-slate-200 bg-white">
        <section className="space-y-2 border-b border-slate-200 p-4" aria-label="Upload">
          <h2 className="text-sm font-semibold">Add a file</h2>
          <select aria-label="Topic" value={uploadTopic} onChange={(e) => setUploadTopic(e.target.value)}
            className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm">
            <option value="">What is it about?</option>
            {topics.map((t) => <option key={t.topic} value={t.topic}>{t.label}</option>)}
          </select>
          <input type="file" aria-label="File" onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            accept=".csv,.txt,.tsv,.xlsx,.xlsm,.kml,.kmz,.geojson,.json,.gpkg,.zip,.shp,.dxf,.pdf,.jpg,.jpeg,.png"
            className="block w-full text-sm" />
          <button onClick={upload} disabled={!file || !uploadTopic || busy}
            className="w-full rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-slate-300">
            Upload
          </button>
          <p className="text-xs text-slate-500">
            CSV, Excel, KML/KMZ, GeoJSON, shapefile (.zip), GeoPackage, AutoCAD .dxf. PDFs and photos are stored but not
            read yet. Or copy files into <code>{dataDir ?? "DATA_DIR"}\raw\</code> and register them below.
          </p>
        </section>

        <section className="min-h-0 flex-1 overflow-y-auto p-4" aria-label="Files">
          {unregistered.length > 0 && (
            <div className="mb-4">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-amber-700">New in the raw folder</h3>
              <ul className="space-y-1">
                {unregistered.map((u) => (
                  <li key={u.path} className="flex items-center justify-between gap-2 rounded bg-amber-50 px-2 py-1 text-sm">
                    <span className="truncate" title={u.path}>{u.name} <span className="text-xs text-slate-500">({u.topic})</span></span>
                    <button onClick={() => register(u.path)} disabled={busy} className="shrink-0 rounded border border-amber-300 px-2 text-xs hover:bg-amber-100">
                      Register
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="mb-1 flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Files</h3>
            <label className="flex items-center gap-1 text-xs text-slate-500">
              <input type="checkbox" checked={showSystem} onChange={(e) => setShowSystem(e.target.checked)} />
              show pipeline downloads
            </label>
          </div>
          {visible.length === 0 && <p className="text-sm text-slate-400">No files yet. Upload one above.</p>}
          <ul className="space-y-1">
            {visible.map((s) => (
              <li key={s.source_id}>
                <button onClick={() => setSelected(s.source_id)}
                  className={`w-full rounded px-2 py-1.5 text-left text-sm hover:bg-slate-100 ${selected === s.source_id ? "bg-blue-50 ring-1 ring-blue-200" : ""}`}>
                  <div className="truncate font-medium">{s.name}</div>
                  <div className="text-xs text-slate-500">
                    {s.topic} · {formatBytes(s.bytes)} · {s.imports.length ? `imported (${s.imports.map((i) => i.layer_id).join(", ")})` : s.system ? "pipeline" : "not imported"}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </section>
        {error && <p className="border-t border-slate-200 p-3 text-sm text-red-600">{error}</p>}
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto bg-slate-50 p-6">
        {!current && (
          <div className="max-w-xl text-sm text-slate-600">
            <h2 className="mb-2 text-lg font-semibold text-slate-800">Data inbox</h2>
            <p>Bring in data from partners in whatever format it comes: road surveys, traffic and pedestrian counts,
              bus stops, schools, waterlogging spots. Each file is kept untouched in the raw folder and recorded with where it
              came from. You then say what it contains, check how its columns match, and import it as a map layer linked to
              the right roads.</p>
            <p className="mt-2">Pick a file on the left, or upload one.</p>
          </div>
        )}
        {current && (
          <div className="max-w-4xl space-y-4 rounded-lg border border-slate-200 bg-white p-5">
            <header>
              <h2 className="text-lg font-semibold">{current.name}</h2>
              <p className="text-xs text-slate-500">
                {current.origin} · received {current.received_at} · licence: {current.licence} · <code>{current.path}</code>
              </p>
            </header>
            <ImportWizard key={current.source_id} cityId={cityId} source={current} layerTypes={layerTypes} system={system}
              onImported={() => { reload(); onDataChanged(); }} onShowOnMap={onShowOnMap} />
          </div>
        )}
      </main>
    </div>
  );
}
