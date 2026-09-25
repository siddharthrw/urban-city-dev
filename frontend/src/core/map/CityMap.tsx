import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import type { City } from "../api";

// Free OSM-based basemap, no API key. Only map tiles are fetched from it; none of our data is sent.
const BASEMAP_STYLE = "https://tiles.openfreemap.org/styles/positron";

// Lets any layer use "pmtiles://<url>" sources (our locally generated vector tiles).
maplibregl.addProtocol("pmtiles", new Protocol().tile);

type Props = {
  city: City;
  onMapReady?: (map: maplibregl.Map) => void;
};

export default function CityMap({ city, onMapReady }: Props) {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!container.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      style: BASEMAP_STYLE,
      center: city.center,
      zoom: city.zoom,
      attributionControl: { compact: true },
    });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "bottom-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
    // "style.load", not "load": our layers only need the style, and "load" waits for every
    // basemap tile, so a slow or failed basemap tile would otherwise keep our data off the map.
    map.once("style.load", () => onMapReady?.(map));
    // Dev-only handle for debugging from the browser console.
    if (import.meta.env.DEV) (window as unknown as { __map: maplibregl.Map }).__map = map;
    return () => map.remove();
    // Re-create the map only when the city changes.
  }, [city.city_id]);

  return <div ref={container} className="h-full w-full" />;
}
