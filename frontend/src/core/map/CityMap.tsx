import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import type { City } from "../api";

// Free OSM-based basemap, no API key. Only map tiles are fetched from it; none of our data is sent.
const BASEMAP_STYLE = "https://tiles.openfreemap.org/styles/positron";

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
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
    map.on("load", () => onMapReady?.(map));
    return () => map.remove();
    // Re-create the map only when the city changes.
  }, [city.city_id]);

  return <div ref={container} className="h-full w-full" />;
}
