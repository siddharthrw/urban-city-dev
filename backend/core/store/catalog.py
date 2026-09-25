"""catalog.duckdb: the index of everything under DATA_DIR.

Tables
  cities         one row per city (Chennai first; more cities = more rows)
  sources        provenance manifest: every file under raw/ with origin, licence, checksum
  layers         built layers per city (GeoParquet path, feature count, build time)
  layer_sources  which raw sources each layer was built from
"""
import shutil
from datetime import datetime, timezone

from core.config import settings
from core.store import db, paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS cities (
    city_id     VARCHAR PRIMARY KEY,
    name        VARCHAR NOT NULL,
    state       VARCHAR,
    country     VARCHAR,
    center_lon  DOUBLE,
    center_lat  DOUBLE,
    zoom        DOUBLE,
    utm_epsg    INTEGER,
    added_at    TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sources (
    source_id     VARCHAR PRIMARY KEY,
    city_id       VARCHAR,
    topic         VARCHAR,
    name          VARCHAR NOT NULL,
    origin        VARCHAR,      -- URL, or who sent it
    received_at   DATE,
    licence       VARCHAR,
    path          VARCHAR NOT NULL,   -- relative to DATA_DIR
    sha256        VARCHAR,
    bytes         BIGINT,
    notes         VARCHAR,
    registered_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS layers (
    city_id        VARCHAR NOT NULL,
    layer_id       VARCHAR NOT NULL,
    topic          VARCHAR NOT NULL,
    path           VARCHAR NOT NULL,  -- relative to DATA_DIR
    geometry_type  VARCHAR,
    feature_count  BIGINT,
    built_at       TIMESTAMP,
    build_script   VARCHAR,
    PRIMARY KEY (city_id, layer_id)
);

CREATE TABLE IF NOT EXISTS layer_sources (
    city_id    VARCHAR NOT NULL,
    layer_id   VARCHAR NOT NULL,
    source_id  VARCHAR NOT NULL,
    PRIMARY KEY (city_id, layer_id, source_id)
);
"""


def init_data_dir() -> None:
    """Create the DATA_DIR layout and catalog if missing. Safe to call every startup."""
    for d in paths.base_dirs():
        d.mkdir(parents=True, exist_ok=True)
    first_time = not settings.catalog_path.exists()
    if first_time:
        db.install_extensions()
    with db.connect() as con:
        con.execute(SCHEMA)


def upsert_city(city: dict, topics: list[str]) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with db.connect() as con:
        con.execute(
            """
            INSERT INTO cities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (city_id) DO UPDATE SET
                name = excluded.name, state = excluded.state, country = excluded.country,
                center_lon = excluded.center_lon, center_lat = excluded.center_lat,
                zoom = excluded.zoom, utm_epsg = excluded.utm_epsg
            """,
            [city["city_id"], city["name"], city.get("state"), city.get("country"),
             city["center"][0], city["center"][1], city.get("zoom", 11),
             city["utm_epsg"], now],
        )
    for topic in topics:
        paths.city_topic_dir(city["city_id"], topic).mkdir(parents=True, exist_ok=True)


def list_cities() -> list[dict]:
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT city_id, name, state, country, center_lon, center_lat, zoom, utm_epsg "
            "FROM cities ORDER BY city_id"
        ).fetchall()
    return [
        {"city_id": r[0], "name": r[1], "state": r[2], "country": r[3],
         "center": [r[4], r[5]], "zoom": r[6], "utm_epsg": r[7]}
        for r in rows
    ]


def health() -> dict:
    """Checks for /health: data dir writable, catalog opens, spatial extension loads."""
    out = {"data_dir": str(settings.data_dir)}
    probe = settings.data_dir / ".write_probe"
    try:
        probe.write_text("ok")
        probe.unlink()
        out["data_dir_writable"] = True
    except OSError as e:
        out["data_dir_writable"] = False
        out["data_dir_error"] = str(e)
    try:
        with db.connect(read_only=True) as con:
            out["duckdb_version"] = con.execute("SELECT version()").fetchone()[0]
            out["spatial_ok"] = con.execute(
                "SELECT ST_AsText(ST_Point(80.27, 13.08))"
            ).fetchone()[0] == "POINT (80.27 13.08)"
    except Exception as e:  # report, don't crash the health check
        out["spatial_ok"] = False
        out["catalog_error"] = str(e)
    out["free_disk_gb"] = round(shutil.disk_usage(settings.data_dir).free / 1e9, 1)
    return out
