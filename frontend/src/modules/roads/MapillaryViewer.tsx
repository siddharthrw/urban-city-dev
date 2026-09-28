import { useEffect, useRef, useState } from "react";
import { Viewer } from "mapillary-js";
import "mapillary-js/dist/mapillary.css";

const TOKEN = (import.meta.env.VITE_MAPILLARY_CLIENT_TOKEN as string) || "";

type Props = {
  lngLat: { lng: number; lat: number };
};

type Status = "loading" | "ok" | "no-coverage" | "error";

function dist2(ax: number, ay: number, bx: number, by: number) {
  return (ax - bx) ** 2 + (ay - by) ** 2;
}

async function queryImages(
  lngLat: { lng: number; lat: number },
  token: string,
  d: number,
  panoOnly: boolean,
) {
  const { lng, lat } = lngLat;
  const pano = panoOnly ? "&is_pano=true" : "";
  const url = `https://graph.mapillary.com/images?access_token=${token}&fields=id,geometry&bbox=${lng-d},${lat-d},${lng+d},${lat+d}${pano}&limit=10`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Mapillary API ${r.status}`);
  const body = await r.json();
  return (body.data ?? []) as { id: string; geometry: { coordinates: [number, number] } }[];
}

async function nearestImageId(lngLat: { lng: number; lat: number }, token: string): Promise<string | null> {
  const { lng, lat } = lngLat;
  // Graduated search: start tight so we find images actually on the clicked road,
  // only expand when nothing is found nearby.
  // Each radius tries 360° panoramas first (best UX), then flat photos.
  for (const d of [0.001, 0.003, 0.005]) {
    let images = await queryImages(lngLat, token, d, true);
    if (!images.length) images = await queryImages(lngLat, token, d, false);
    if (images.length) {
      images.sort((a, b) =>
        dist2(lng, lat, ...a.geometry.coordinates) - dist2(lng, lat, ...b.geometry.coordinates)
      );
      return images[0].id;
    }
  }
  return null;
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
          component: {
            cover: false,
            sequence: true,   // forward/back arrows to walk along the street
            direction: true,  // turn arrows to take different routes at junctions
            bearing: true,    // compass
          },
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

  // cbll = camera ball location → opens Google Maps directly in Street View mode.
  // Google snaps to the nearest covered road — as precise as possible without a paid API.
  const gmapsUrl = `https://www.google.com/maps?layer=c&cbll=${lngLat.lat},${lngLat.lng}&cbp=12,0,,0,0&z=18`;

  return (
    <div className="space-y-1">
      <div className="relative h-56 overflow-hidden rounded-md">
        {/* Container is always visible so the WebGL context gets a real size on init. */}
        <div ref={containerRef} className="h-full w-full" />

        {/* Overlay — covers the viewer while loading or when there's no coverage. */}
        {status !== "ok" && (
          <div className={`absolute inset-0 flex flex-col items-center justify-center gap-2 text-xs
            ${status === "error" ? "bg-red-50 px-3 text-red-700" : "bg-slate-100 text-slate-400"}`}>
            {status === "loading" && "Finding street view…"}
            {status === "error" && errorMsg}
            {status === "no-coverage" && <span>No Mapillary imagery near this road</span>}
          </div>
        )}
      </div>

      <a
        href={gmapsUrl}
        target="_blank"
        rel="noreferrer"
        className="flex items-center justify-center gap-1 rounded-md border border-slate-200 py-1 text-xs text-slate-500 hover:bg-slate-50 hover:text-slate-700"
      >
        Open in Google Street View ↗
      </a>
    </div>
  );
}
