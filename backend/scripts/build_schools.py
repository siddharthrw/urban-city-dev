"""Build the Chennai schools layer from two GCC KML files.

Source: Greater Chennai Corporation via OpenCity (public domain), downloaded 2026-09-29.
  - all_schools.kml   All schools in Chennai (corporation, aided, unaided) — full coverage
  - gcc_schools.kml   GCC corporation schools with student enrollment breakdown

Strategy: import all_schools as the base; enrich with enrollment from gcc_schools
by spatial join (nearest GCC school within 100m gets its enrollment data).

Run from the repo root:
  python -m scripts.build_schools
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
LAYER_ID = "schools"
TOPIC = "surroundings"
RAW_DIR = settings.data_dir / "raw" / "opencity_gcc_schools" / "2026-09-29"

SOURCE_ALL = "gcc_schools_all_2026"
SOURCE_GCC = "gcc_schools_corp_2026"


def main() -> None:
    catalog.init_data_dir()

    # --- All schools (full coverage) ---
    print("  reading all_schools.kml …", end=" ", flush=True)
    all_schools = gpd.read_file(RAW_DIR / "all_schools.kml", driver="KML")
    all_schools = all_schools[all_schools.geometry.notna()].copy()
    all_schools = all_schools.to_crs("EPSG:4326")
    print(f"{len(all_schools)} features")

    all_schools["school_name"] = all_schools.get("SCHOOL_NAM", pd.Series(dtype=str)).fillna("")
    all_schools["management"]  = all_schools.get("MANAGEMENT",  pd.Series(dtype=str)).fillna("")
    all_schools["category"]    = all_schools.get("CATEGORY",    pd.Series(dtype=str)).fillna("")
    all_schools["address"]     = ""
    all_schools["students"]    = pd.NA
    all_schools["notes"]       = (
        all_schools.get("BLOCK", pd.Series(dtype=str)).fillna("") + " · " +
        all_schools.get("P_NAME_RD", pd.Series(dtype=str)).fillna("")
    ).str.strip(" ·")

    # --- GCC corporation schools (has enrollment) ---
    print("  reading gcc_schools.kml …", end=" ", flush=True)
    gcc = gpd.read_file(RAW_DIR / "gcc_schools.kml", driver="KML")
    gcc = gcc[gcc.geometry.notna()].copy()
    gcc = gcc.to_crs("EPSG:32644")   # UTM for metre-based join
    print(f"{len(gcc)} features")

    # Reproject all_schools to UTM for spatial join, then back
    all_utm = all_schools.to_crs("EPSG:32644")
    joined = gpd.sjoin_nearest(all_utm, gcc[["TOT", "ADDR", "geometry"]], how="left", max_distance=100)

    # Fill enrollment and address where the join found a match
    mask = joined["TOT"].notna()
    all_schools.loc[mask, "students"] = joined.loc[mask, "TOT"].astype("Int64")
    all_schools.loc[mask, "address"]  = joined.loc[mask, "ADDR"].fillna("")

    combined = all_schools[["school_name", "management", "category", "students",
                             "address", "notes", "geometry"]].copy()
    combined = gpd.GeoDataFrame(combined, geometry="geometry", crs="EPSG:4326")

    # --- Register sources ---
    for source_id, filename, name, notes in [
        (SOURCE_ALL, "all_schools.kml",
         "Map of All Schools in Chennai (GCC / OpenCity)",
         "All corporation, aided and unaided schools. Samgra Shiksha data."),
        (SOURCE_GCC, "gcc_schools.kml",
         "GCC Schools Map (GCC / OpenCity)",
         "GCC corporation schools with student enrollment breakdown."),
    ]:
        catalog.register_source(
            source_id=source_id, file=RAW_DIR / filename, name=name,
            origin="https://data.opencity.in/dataset/chennai-schools",
            licence="Public Domain (no licence provided by GCC)",
            received_at=date(2026, 9, 29), topic=TOPIC, city_id=CITY_ID, notes=notes,
        )

    # --- Write layer ---
    out_path = paths.city_topic_dir(CITY_ID, TOPIC) / "layers" / "schools.parquet"
    layers.write_geoparquet(combined, out_path)

    catalog.record_layer(
        city_id=CITY_ID, layer_id=LAYER_ID, topic=TOPIC, file=out_path,
        geometry_type="Point", feature_count=len(combined),
        build_script="scripts/build_schools.py",
        source_ids=[SOURCE_ALL, SOURCE_GCC],
    )

    with_enrollment = combined["students"].notna().sum()
    print(f"\nDone — {len(combined)} schools saved to {out_path}")
    print(f"  {with_enrollment} schools have enrollment data")
    print(f"  {len(combined) - with_enrollment} schools without enrollment (aided/unaided)")


if __name__ == "__main__":
    main()
