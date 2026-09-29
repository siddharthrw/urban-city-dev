"""Build the Chennai parks layer from three GCC KML files.

Source: Greater Chennai Corporation via OpenCity (public domain), downloaded 2026-09-29.
  - neighbourhood_parks.kml  (< 4,000 sq m)
  - community_parks.kml      (4,000 – 8,000 sq m)
  - city_parks.kml           (> 8,000 sq m)

Run from the repo root:
  python -m scripts.build_parks
"""
import sys
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import settings
from core.store import catalog, layers, paths

CITY_ID = "chennai"
LAYER_ID = "parks"
TOPIC = "surroundings"
RAW_DIR = settings.data_dir / "raw" / "opencity_gcc_parks" / "2026-09-29"

SOURCES = [
    ("neighbourhood_parks.kml",  "neighbourhood", "gcc_parks_neighbourhood_2026"),
    ("community_parks.kml",      "community",     "gcc_parks_community_2026"),
    ("city_parks.kml",           "city",          "gcc_parks_city_2026"),
]

AREA_FIELD = "GIS_Neighbourhoodparks_545_160519_AREA"


def _read_kml(path: Path, park_type: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path, driver="KML")
    gdf = gdf[gdf.geometry.notna()].copy()
    gdf = gdf.to_crs("EPSG:4326")

    # Normalise to a consistent schema across all three files.
    area_col = next((c for c in gdf.columns if "AREA" in c.upper()), None)
    gdf["park_name"]     = gdf.get("PARK_NAME", pd.Series(dtype=str)).fillna("")
    gdf["park_type"]     = park_type
    gdf["area_sqm"]      = gdf[area_col].astype(float).round(1) if area_col else None
    gdf["maintained_by"] = gdf.get("MAINTAINED", pd.Series(dtype=str)).fillna("")
    gdf["address"]       = gdf.get("ADDRESS",   pd.Series(dtype=str)).fillna("")

    return gdf[["park_name", "park_type", "area_sqm", "maintained_by", "address", "geometry"]]


def main() -> None:
    catalog.init_data_dir()

    frames = []
    source_ids = []
    for filename, park_type, source_id in SOURCES:
        kml_path = RAW_DIR / filename
        print(f"  reading {filename} …", end=" ", flush=True)
        gdf = _read_kml(kml_path, park_type)
        print(f"{len(gdf)} features")
        frames.append(gdf)

        catalog.register_source(
            source_id=source_id,
            file=kml_path,
            name=f"Chennai {park_type.capitalize()} Parks Map (GCC / OpenCity)",
            origin="https://data.opencity.in/dataset/chennai-parks",
            licence="Public Domain (no licence provided by GCC)",
            received_at=date(2026, 9, 29),
            topic=TOPIC,
            city_id=CITY_ID,
            notes=f"KML of {park_type} parks in Chennai. Updated Nov 2025 on OpenCity.",
        )
        source_ids.append(source_id)

    combined = pd.concat(frames, ignore_index=True)
    combined = gpd.GeoDataFrame(combined, geometry="geometry", crs="EPSG:4326")

    out_path = paths.city_topic_dir(CITY_ID, TOPIC) / "layers" / "parks.parquet"
    layers.write_geoparquet(combined, out_path)

    catalog.record_layer(
        city_id=CITY_ID,
        layer_id=LAYER_ID,
        topic=TOPIC,
        file=out_path,
        geometry_type="Polygon",
        feature_count=len(combined),
        build_script="scripts/build_parks.py",
        source_ids=source_ids,
    )

    by_type = combined["park_type"].value_counts()
    print(f"\nDone — {len(combined)} parks saved to {out_path}")
    for t, n in by_type.items():
        print(f"  {t}: {n}")


if __name__ == "__main__":
    main()
