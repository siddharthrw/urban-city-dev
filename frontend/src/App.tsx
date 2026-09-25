import { useEffect, useState } from "react";
import { api, type City, type Health, type SystemInfo, type Topic } from "./core/api";
import CityMap from "./core/map/CityMap";

export default function App() {
  const [cities, setCities] = useState<City[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.cities(), api.topics(), api.health(), api.system()])
      .then(([c, t, h, s]) => {
        setCities(c);
        setTopics(t);
        setHealth(h);
        setSystem(s);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const city = cities[0];

  return (
    <div className="flex h-full font-sans text-slate-800">
      <aside className="flex w-80 shrink-0 flex-col border-r border-slate-200 bg-white">
        <header className="border-b border-slate-200 px-4 py-3">
          <h1 className="text-lg font-semibold">City Planning OS</h1>
          <p className="text-sm text-slate-500">{city ? `${city.name}, ${city.state}` : "Loading…"}</p>
        </header>

        <section className="flex-1 overflow-y-auto px-4 py-3">
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Layers</h2>
          {topics.map((t) => (
            <div key={t.topic} className="mb-3">
              <div className="text-sm font-medium">{t.label}</div>
              <div className="text-xs text-slate-400">No layers yet</div>
            </div>
          ))}
        </section>

        <footer className="space-y-1 border-t border-slate-200 px-4 py-2 text-xs text-slate-500">
          {error && <div className="text-red-600">Backend not reachable: {error}</div>}
          {health && (
            <div className="flex items-center gap-2">
              <span className={`inline-block h-2 w-2 rounded-full ${health.status === "ok" ? "bg-green-500" : "bg-amber-500"}`} />
              Backend {health.status} · v{health.version}
            </div>
          )}
          {health && <div title="All data is stored here, on this machine">Data: {health.data_dir}</div>}
          {system && (
            <div className={system.llm_is_external ? "font-medium text-amber-700" : ""}>
              AI: {system.llm_is_external ? `${system.llm_provider} (external; prompt text leaves this machine)` : "local (Ollama)"}
            </div>
          )}
        </footer>
      </aside>

      <main className="relative flex-1">{city && <CityMap city={city} />}</main>
    </div>
  );
}
