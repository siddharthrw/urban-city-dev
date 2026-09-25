import { useState } from "react";
import { linkMethodLabel } from "../format";
import { inboxApi, type ImportRecord, type Street, type UnmatchedRow } from "./api";

type Props = {
  cityId: string;
  record: ImportRecord;
  onChanged: (r: ImportRecord) => void;
  onDeleted: () => void;
  onShowOnMap: (lon: number, lat: number) => void;
};

export default function ImportResult({ cityId, record, onChanged, onDeleted, onShowOnMap }: Props) {
  const s = record.stats;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const remove = async () => {
    if (!confirm("Remove this import from the map? The original file stays in the raw folder.")) return;
    setBusy(true);
    try {
      await inboxApi.deleteImport(cityId, record.import_id);
      onDeleted();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4" aria-label="Import result">
      {s.is_sample && (
        <div className="rounded-md border border-orange-200 bg-orange-50 px-3 py-2 text-sm text-orange-900">
          This file is <b>SAMPLE, made-up test data</b>. It is labelled as such everywhere it appears.
        </div>
      )}
      <div className="grid grid-cols-3 gap-2 text-center sm:grid-cols-6">
        <Stat label="Rows in file" value={s.rows_in_file} />
        <Stat label="Imported" value={s.imported} />
        <Stat label="Rejected" value={s.invalid} tone={s.invalid ? "bad" : undefined} />
        <Stat label="Linked to roads" value={s.linked} tone="good" />
        <Stat label="Need a road" value={s.unmatched} tone={s.unmatched ? "warn" : undefined} />
        <Stat label="On the map" value={s.on_map} />
      </div>
      {Object.keys(s.by_link_method).length > 0 && (
        <p className="text-xs text-slate-500">
          Linked {Object.entries(s.by_link_method).map(([k, v]) => `${v} ${linkMethodLabel(k)}`).join(", ")}.
        </p>
      )}
      {s.effects?.verified_segments != null && (
        <p className="rounded-md bg-green-50 px-3 py-2 text-sm text-green-900">
          {s.effects.verified_segments} road segments now have a <b>verified</b> width from this survey.
        </p>
      )}
      {s.warnings.map((w) => (
        <p key={w} className="text-xs text-amber-700">{w}</p>
      ))}

      {record.problems.invalid.length > 0 && (
        <section>
          <h4 className="mb-1 text-sm font-semibold">Rejected rows (fix them in the file and import again)</h4>
          <ul className="space-y-1 text-sm">
            {record.problems.invalid.map((p) => (
              <li key={p.row_no}>
                <span className="font-mono text-xs text-slate-500">row {p.row_no}</span> {p.errors.join("; ")}
              </li>
            ))}
          </ul>
        </section>
      )}

      {record.problems.unmatched.length > 0 && (
        <section>
          <h4 className="mb-1 text-sm font-semibold">Rows not linked to a road</h4>
          <ul className="space-y-3">
            {record.problems.unmatched.map((u) => (
              <UnmatchedItem key={u.row_no} cityId={cityId} importId={record.import_id} row={u}
                onChanged={onChanged} onShowOnMap={onShowOnMap} />
            ))}
          </ul>
        </section>
      )}

      {error && <p className="text-sm text-red-600">{error}</p>}
      <button onClick={remove} disabled={busy} className="rounded border border-red-300 px-3 py-1.5 text-sm text-red-700 hover:bg-red-50">
        Remove this import
      </button>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: "good" | "warn" | "bad" }) {
  const color = tone === "good" ? "text-green-700" : tone === "warn" ? "text-amber-700" : tone === "bad" ? "text-red-700" : "text-slate-800";
  return (
    <div className="rounded-md border border-slate-200 px-2 py-2">
      <div className={`text-xl font-semibold ${color}`}>{value}</div>
      <div className="text-xs text-slate-500">{label}</div>
    </div>
  );
}

export function UnmatchedItem({ cityId, importId, row, onChanged, onShowOnMap }: {
  cityId: string;
  importId: string;
  row: UnmatchedRow;
  onChanged: (r: ImportRecord) => void;
  onShowOnMap: (lon: number, lat: number) => void;
}) {
  const [q, setQ] = useState(row.road_name ?? "");
  const [options, setOptions] = useState<Street[]>(row.candidates);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const find = async () => {
    if (q.trim().length < 2) return;
    setBusy(true);
    try {
      const r = await inboxApi.streets(cityId, q.trim());
      setOptions(r.streets);
      setNote(r.note ?? (r.streets.length ? null : "No road found with that name."));
    } catch (e) {
      setNote((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const pick = async (s: Street) => {
    setBusy(true);
    try {
      onChanged(await inboxApi.linkRow(cityId, importId, row.row_no, s));
    } catch (e) {
      setNote((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <li className="rounded-md border border-slate-200 p-2 text-sm">
      <div>
        <span className="font-mono text-xs text-slate-500">row {row.row_no}</span>{" "}
        {row.road_name ? <b>{row.road_name}</b> : <i>no road name</i>}
        <span className="text-slate-500"> — {row.reason}</span>
      </div>
      <div className="mt-2 flex gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && find()}
          placeholder="Link to road named…"
          aria-label={`Road name for row ${row.row_no}`}
          className="flex-1 rounded border border-slate-300 px-2 py-1 text-sm"
        />
        <button onClick={find} disabled={busy} className="rounded border border-slate-300 px-2 py-1 text-sm hover:bg-slate-50">
          Find
        </button>
      </div>
      {note && <p className="mt-1 text-xs text-slate-500">{note}</p>}
      {options.length > 0 && (
        <ul className="mt-2 space-y-1">
          {options.map((s, i) => (
            <li key={`${s.road_name}-${i}`} className="flex items-center justify-between gap-2 rounded bg-slate-50 px-2 py-1">
              <span className="text-xs">
                <b>{s.road_name ?? "Unnamed"}</b> · {(s.length_m / 1000).toFixed(2)} km · near {s.lat.toFixed(4)}, {s.lon.toFixed(4)}
              </span>
              <span className="flex shrink-0 gap-1">
                <button onClick={() => onShowOnMap(s.lon, s.lat)} className="rounded px-1.5 text-xs text-blue-700 hover:underline">
                  map
                </button>
                <button onClick={() => pick(s)} disabled={busy} className="rounded bg-blue-600 px-2 py-0.5 text-xs text-white hover:bg-blue-700">
                  Link
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
