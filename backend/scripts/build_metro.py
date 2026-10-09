"""Build the Chennai metro stations layer from the station list in DATA_DIR.

Source: the Chennai Metro Rail station list supplied by the project owner (Blue and Green lines,
from the CMRL station board). Coordinates are not in that list: each one comes from the
OpenStreetMap point named in `coordinate_source` (OpenStreetMap contributors, ODbL, 2026-10-07).

Only stations in the file are included. Phase 2 and any stations not yet in the list are
added by editing the CSV and rerunning this script.

Run from the repo root:
  python -m scripts.build_metro
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
LAYER_ID = "metro_stations"
TOPIC = "surroundings"
RAW_DIR = settings.data_dir / "raw" / "chennai_metro_stations" / "2026-10-07"
RAW_FILE = RAW_DIR / "stations_from_user_list.csv"
SOURCE_ID = "cmrl_station_list_2026"


def load_stations(raw_file: Path) -> gpd.GeoDataFrame:
    """Read the station CSV and return one row per station, in EPSG:4326."""
    df = pd.read_csv(raw_file, dtype=str, encoding="utf-8")
    df["lat"] = df["lat"].astype(float)
    df["lon"] = df["lon"].astype(float)
    geometry = gpd.points_from_xy(df["lon"], df["lat"])
    return gpd.GeoDataFrame(df[["station_name", "line", "coordinate_source"]],
                            geometry=geometry, crs="EPSG:4326")


def validate_stations(stations: gpd.GeoDataFrame) -> None:
    """Stop the build if the list has a gap, a repeated name, or a point outside Greater Chennai."""
    if stations.empty:
        raise ValueError("station list is empty")
    if (stations["station_name"].str.strip() == "").any():
        raise ValueError("a station has no name")
    if not stations["station_name"].is_unique:
        dupes = stations.loc[stations["station_name"].duplicated(), "station_name"].tolist()
        raise ValueError(f"duplicate station names: {dupes}")
    if not stations["line"].isin(["Blue", "Green", "Blue;Green"]).all():
        raise ValueError("a station has an unknown line (expected Blue, Green or Blue;Green)")
    minx, miny, maxx, maxy = 80.0, 12.8, 80.4, 13.3
    outside = stations[(stations.geometry.x < minx) | (stations.geometry.x > maxx)
                       | (stations.geometry.y < miny) | (stations.geometry.y > maxy)]
    if not outside.empty:
        raise ValueError(f"locations outside Greater Chennai: {outside['station_name'].tolist()}")


def main() -> None:
    catalog.init_data_dir()

    stations = load_stations(RAW_FILE)
    validate_stations(stations)
    print(f"  {len(stations)} stations read and checked from {RAW_FILE.name}")

    catalog.register_source(
        source_id=SOURCE_ID, file=RAW_FILE, name="Chennai Metro stations (CMRL station list)",
        origin="Station list supplied by the project owner; coordinates from OpenStreetMap",
        licence="Station names: owner-supplied. Coordinates: ODbL (OpenStreetMap contributors)",
        received_at=date(2026, 10, 7), topic=TOPIC, city_id=CITY_ID,
        notes="Blue and Green lines only. Green Line list was incomplete when supplied.",
    )

    out_path = paths.city_topic_dir(CITY_ID, TOPIC) / "layers" / "metro_stations.parquet"
    layers.write_geoparquet(stations, out_path)

    catalog.record_layer(
        city_id=CITY_ID, layer_id=LAYER_ID, topic=TOPIC, file=out_path,
        geometry_type="Point", feature_count=len(stations),
        build_script="scripts/build_metro.py", source_ids=[SOURCE_ID],
    )
    print(f"\nDone — {len(stations)} metro stations saved to {out_path}")


if __name__ == "__main__":
    main()
