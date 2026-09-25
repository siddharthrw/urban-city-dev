"""catalog.duckdb: the index of everything under DATA_DIR.

Tables
  cities         one row per city (Chennai first; more cities = more rows)
  sources        provenance manifest: every file under raw/ with origin, licence, checksum
  layers         built layers per city (GeoParquet path, feature count, build time)
  layer_sources  which raw sources each layer was built from
  feature_overrides  human/survey values (e.g. verified widths) that survive rebuilds
"""
import hashlib
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

from core.config import settings
from core.store import db, paths


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

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

-- Human-entered or surveyed values that must survive layer rebuilds (e.g. verified road widths).
-- Layer builds read these and apply them on top of whatever the pipeline computes.
CREATE TABLE IF NOT EXISTS feature_overrides (
    city_id     VARCHAR NOT NULL,
    layer_id    VARCHAR NOT NULL,
    feature_id  VARCHAR NOT NULL,
    attribute   VARCHAR NOT NULL,
    value_num   DOUBLE,
    detail      VARCHAR,      -- who/what/how, shown in the UI
    source_id   VARCHAR,      -- raw file it came from, if imported
    entered_at  TIMESTAMP,
    PRIMARY KEY (city_id, layer_id, feature_id, attribute)
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
    now = _now()
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


def register_source(
    *, source_id: str, file: Path, name: str, origin: str, licence: str,
    received_at: date, topic: str, city_id: str | None = None, notes: str = "",
) -> None:
    """Add (or refresh) one raw file in the provenance manifest, with its checksum."""
    with db.connect() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [source_id, city_id, topic, name, origin, received_at, licence,
             paths.relative(file), sha256_file(file), file.stat().st_size, notes, _now()],
        )


def record_layer(
    *, city_id: str, layer_id: str, topic: str, file: Path, geometry_type: str,
    feature_count: int, build_script: str, source_ids: list[str],
) -> None:
    """Record a (re)built layer and replace its source links, so re-runs stay clean."""
    with db.connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO layers VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [city_id, layer_id, topic, paths.relative(file), geometry_type,
             feature_count, _now(), build_script],
        )
        con.execute("DELETE FROM layer_sources WHERE city_id = ? AND layer_id = ?", [city_id, layer_id])
        for sid in source_ids:
            con.execute("INSERT INTO layer_sources VALUES (?, ?, ?)", [city_id, layer_id, sid])


def get_layer(city_id: str, layer_id: str) -> dict | None:
    with db.connect(read_only=True) as con:
        row = con.execute(
            "SELECT topic, path, geometry_type, feature_count, built_at FROM layers "
            "WHERE city_id = ? AND layer_id = ?",
            [city_id, layer_id],
        ).fetchone()
        if not row:
            return None
        sources = con.execute(
            """
            SELECT s.source_id, s.name, s.origin, s.licence, s.received_at
            FROM layer_sources ls JOIN sources s USING (source_id)
            WHERE ls.city_id = ? AND ls.layer_id = ?
            ORDER BY s.source_id
            """,
            [city_id, layer_id],
        ).fetchall()
    return {
        "city_id": city_id, "layer_id": layer_id, "topic": row[0],
        "path": settings.data_dir / row[1], "geometry_type": row[2],
        "feature_count": row[3], "built_at": row[4],
        "sources": [
            {"source_id": s[0], "name": s[1], "origin": s[2], "licence": s[3], "received_at": s[4]}
            for s in sources
        ],
    }


def list_layers(city_id: str) -> list[dict]:
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT layer_id FROM layers WHERE city_id = ? ORDER BY topic, layer_id", [city_id]
        ).fetchall()
    return [get_layer(city_id, r[0]) for r in rows]


def get_overrides(city_id: str, layer_id: str, attribute: str) -> dict[str, dict]:
    """feature_id -> {value, detail} for one attribute of one layer."""
    with db.connect(read_only=True) as con:
        rows = con.execute(
            "SELECT feature_id, value_num, detail FROM feature_overrides "
            "WHERE city_id = ? AND layer_id = ? AND attribute = ?",
            [city_id, layer_id, attribute],
        ).fetchall()
    return {r[0]: {"value": r[1], "detail": r[2]} for r in rows}


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
