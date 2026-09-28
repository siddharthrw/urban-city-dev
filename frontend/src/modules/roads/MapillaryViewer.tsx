import { useEffect, useRef, useState } from "react";
import { Viewer } from "mapillary-js";
import "mapillary-js/dist/mapillary.css";

const TOKEN = (import.meta.env.VITE_MAPILLARY_CLIENT_TOKEN as string) || "";

type Props = {
  lngLat: { lng: number; lat: number };
};

type Status = "loading" | "ok" | "no-coverage" | "error";

async function nearestImageId(lngLat: { lng: number; lat: number }, token: string): Promise<string | null> {
  // bbox with ~550 m half-width — wide enough to find images in cities with sparse coverage.
  const { lng, lat } = lngLat;
  const d = 0.005;
  const url = `https://graph.mapillary.com/images?access_token=${token}&fields=id,geometry&bbox=${lng-d},${lat-d},${lng+d},${lat+d}&limit=1`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Mapillary API ${r.status}`);
  const body = await r.json();
  return (body.data?.[0]?.id as string) ?? null;
}

export default function MapillaryViewer({ lngLat }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const [status, setStatus] = useState<Status>("loading");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    if (!TOKEN) return;
    let cancelled = false;
    setStatus("loading");

    nearestImageId(lngLat, TOKEN)
      .then((imageId) => {
        if (cancelled) return;
        if (!imageId) { setStatus("no-coverage"); return; }
        if (!containerRef.current) return;

        // Remove previous viewer before creating a new one in the same container.
        viewerRef.current?.remove();
        viewerRef.current = null;

        const viewer = new Viewer({
          accessToken: TOKEN,
          container: containerRef.current,
          imageId,
          component: { cover: false },
        });
        viewerRef.current = viewer;
        setStatus("ok");
      })
      .catch((e: Error) => {
        if (!cancelled) { setStatus("error"); setErrorMsg(e.message); }
      });

    return () => {
      cancelled = true;
      viewerRef.current?.remove();
      viewerRef.current = null;
    };
  }, [lngLat.lng, lngLat.lat]);

  if (!TOKEN) {
    return (
      <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-500">
        Add <code className="rounded bg-slate-100 px-1">VITE_MAPILLARY_CLIENT_TOKEN</code> to your{" "}
        <code className="rounded bg-slate-100 px-1">.env</code> to enable street view.{" "}
        Get a free token at{" "}
        <a href="https://www.mapillary.com/dashboard/developers" target="_blank" rel="noreferrer"
          className="text-blue-600 hover:underline">
          mapillary.com/dashboard/developers
        </a>.
      </div>
    );
  }

  return (
    <div className="relative overflow-hidden rounded-md">
      {/* Viewer container — always in DOM so Mapillary has a stable node */}
      <div ref={containerRef} className="h-56 w-full" style={{ display: status === "ok" ? "block" : "none" }} />

      {status === "loading" && (
        <div className="flex h-56 items-center justify-center bg-slate-100 text-xs text-slate-400">
          Finding street view…
        </div>
      )}
      {status === "no-coverage" && (
        <div className="flex h-56 items-center justify-center bg-slate-100 text-xs text-slate-400">
          No street imagery near this road
        </div>
      )}
      {status === "error" && (
        <div className="flex h-56 items-center justify-center bg-red-50 px-3 text-xs text-red-700">
          {errorMsg}
        </div>
      )}
    </div>
  );
}
