import { useEffect, useState } from "react";
import { roadsApi, type SearchHit } from "./api";

type Props = {
  cityId: string;
  onPick: (hit: SearchHit) => void;
};

export default function RoadSearch({ cityId, onPick }: Props) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) {
      setHits([]);
      return;
    }
    const t = setTimeout(() => {
      roadsApi.search(cityId, term).then(setHits).catch(() => setHits([]));
    }, 200);
    return () => clearTimeout(t);
  }, [q, cityId]);

  return (
    <div className="relative">
      <input
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        placeholder="Search a road by name…"
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
      />
      {open && hits.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-80 w-full overflow-y-auto rounded-md border border-slate-200 bg-white shadow-lg">
          {hits.map((h) => (
            <li key={h.name}>
              <button
                className="w-full px-3 py-2 text-left text-sm hover:bg-slate-100"
                onClick={() => {
                  onPick(h);
                  setQ(h.name);
                  setOpen(false);
                }}
              >
                <div className="font-medium">{h.name}</div>
                <div className="text-xs text-slate-500">
                  {h.road_class.replace("_", " ")} · {(h.length_m / 1000).toFixed(1)} km · {h.segments} segments
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
      {open && q.trim().length >= 2 && hits.length === 0 && (
        <div className="absolute z-20 mt-1 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500 shadow">
          No named road matches. Only about a third of Chennai's road segments have a name in OSM.
        </div>
      )}
    </div>
  );
}
