"""catalog.duckdb: the index of everything under DATA_DIR.

Tables
  cities         one row per city (Chennai first; more cities = more rows)
  sources        provenance manifest: every file under raw/ with origin, licence, checksum
  layers         built layers per city (GeoParquet path, feature count, build time)
  layer_sources  which raw sources each layer was built from
  feature_overrides  human/survey values (e.g. verified widths) that survive rebuilds
"""
import hashlib
import json
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
    registered_at TIMESTAMP,
    -- Standards-document metadata (topic='standards'); NULL for everything else.
    -- "Superseded documents are never cited": authority is what a rule's citation checks.
    authority     VARCHAR,      -- active | superseded (a document's status, distinct from a rule's authority)
    doc_year      INTEGER,
    jurisdiction  VARCHAR       -- e.g. "India", "Tamil Nadu", "Chennai"
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

-- Data inbox: one row per (source file, target layer, sheet). Re-importing replaces it.
CREATE TABLE IF NOT EXISTS imports (
    import_id   VARCHAR PRIMARY KEY,
    city_id     VARCHAR NOT NULL,
    source_id   VARCHAR NOT NULL,
    layer_id    VARCHAR NOT NULL,
    sheet       VARCHAR,
    mapping     VARCHAR,      -- JSON {field: column}
    options     VARCHAR,      -- JSON (e.g. {"crs": "EPSG:32644"})
    status      VARCHAR,      -- imported | failed
    stats       VARCHAR,      -- JSON counts
    problems    VARCHAR,      -- JSON {invalid: [...], unmatched: [...]}
    created_at  TIMESTAMP,
    updated_at  TIMESTAMP
);

-- A person's fix for a row the inbox could not link to a road. Survives re-imports.
CREATE TABLE IF NOT EXISTS import_links (
    import_id   VARCHAR NOT NULL,
    row_no      INTEGER NOT NULL,
    seg_ids     VARCHAR[],
    road_name   VARCHAR,
    created_at  TIMESTAMP,
    PRIMARY KEY (import_id, row_no)
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
        _migrate(con)


def _migrate(con) -> None:
    """Non-destructive column additions for catalogs created before they existed."""
    for col, typ in [("authority", "VARCHAR"), ("doc_year", "INTEGER"), ("jurisdiction", "VARCHAR")]:
        con.execute(f"ALTER TABLE sources ADD COLUMN IF NOT EXISTS {col} {typ}")


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
    authority: str | None = None, doc_year: int | None = None, jurisdiction: str | None = None,
) -> None:
    """Add (or refresh) one raw file in the provenance manifest, with its checksum.
    authority/doc_year/jurisdiction are for standards documents (topic='standards'); a document's
    authority is active|superseded (its own status), distinct from a rule's source.authority."""
    with db.connect() as con:
        con.execute(
            """
            INSERT OR REPLACE INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [source_id, city_id, topic, name, origin, received_at, licence,
             paths.relative(file), sha256_file(file), file.stat().st_size, notes, _now(),
             authority, doc_year, jurisdiction],
        )


def latest_source(prefix: str) -> dict | None:
    """Newest registered source whose id starts with prefix (e.g. the latest GCC centerline)."""
    with db.connect(read_only=True) as con:
        row = con.execute(
            "SELECT source_id, name, path, received_at, licence FROM sources "
            "WHERE starts_with(source_id, ?) ORDER BY received_at DESC, registered_at DESC LIMIT 1",
            [prefix],
        ).fetchone()
    if not row:
        return None
    return {"source_id": row[0], "name": row[1], "path": settings.data_dir / row[2],
            "received_at": row[3], "licence": row[4]}


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


def get_source(source_id: str) -> dict | None:
    with db.connect(read_only=True) as con:
        cur = con.execute("SELECT * FROM sources WHERE source_id = ?", [source_id])
        row = cur.fetchone()
        cols = [d[0] for d in cur.description]
    if not row:
        return None
    out = dict(zip(cols, row))
    out["abs_path"] = settings.data_dir / out["path"]
    return out


def rename_source(source_id: str, name: str) -> None:
    """Give a registered file a human-chosen display name (e.g. a document's real title),
    kept separate from its filename on disk."""
    with db.connect() as con:
        con.execute("UPDATE sources SET name = ? WHERE source_id = ?", [name, source_id])


def list_sources(city_id: str | None = None) -> list[dict]:
    with db.connect(read_only=True) as con:
        cur = con.execute(
            "SELECT * FROM sources WHERE ? IS NULL OR city_id = ? OR city_id IS NULL "
            "ORDER BY registered_at DESC", [city_id, city_id])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def registered_paths() -> set[str]:
    with db.connect(read_only=True) as con:
        return {r[0] for r in con.execute("SELECT path FROM sources").fetchall()}


def delete_layer_record(city_id: str, layer_id: str) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM layers WHERE city_id = ? AND layer_id = ?", [city_id, layer_id])
        con.execute("DELETE FROM layer_sources WHERE city_id = ? AND layer_id = ?", [city_id, layer_id])


# ---------- overrides ----------

def replace_overrides(city_id: str, layer_id: str, attribute: str, source_id: str,
                      values: dict[str, tuple[float, str]]) -> None:
    """Replace every override that came from source_id with {feature_id: (value, detail)}."""
    now = _now()
    with db.connect() as con:
        con.execute(
            "DELETE FROM feature_overrides WHERE city_id = ? AND layer_id = ? AND attribute = ? AND source_id = ?",
            [city_id, layer_id, attribute, source_id])
        for fid, (value, detail) in values.items():
            con.execute(
                "INSERT OR REPLACE INTO feature_overrides VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [city_id, layer_id, fid, attribute, value, detail, source_id, now])


# ---------- imports ----------

def save_import(rec: dict) -> None:
    now = _now()
    with db.connect() as con:
        existing = con.execute("SELECT created_at FROM imports WHERE import_id = ?", [rec["import_id"]]).fetchone()
        con.execute(
            "INSERT OR REPLACE INTO imports VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [rec["import_id"], rec["city_id"], rec["source_id"], rec["layer_id"], rec.get("sheet"),
             json.dumps(rec.get("mapping", {})), json.dumps(rec.get("options", {})), rec["status"],
             json.dumps(rec.get("stats", {}), default=str), json.dumps(rec.get("problems", {}), default=str),
             existing[0] if existing else now, now])


def _import_row(cols, row) -> dict:
    d = dict(zip(cols, row))
    for k in ("mapping", "options", "stats", "problems"):
        d[k] = json.loads(d[k]) if d[k] else {}
    return d


def get_import(import_id: str) -> dict | None:
    with db.connect(read_only=True) as con:
        cur = con.execute("SELECT * FROM imports WHERE import_id = ?", [import_id])
        row = cur.fetchone()
        cols = [d[0] for d in cur.description]
    return _import_row(cols, row) if row else None


def list_imports(city_id: str, layer_id: str | None = None) -> list[dict]:
    with db.connect(read_only=True) as con:
        cur = con.execute(
            "SELECT * FROM imports WHERE city_id = ? AND (? IS NULL OR layer_id = ?) ORDER BY updated_at DESC",
            [city_id, layer_id, layer_id])
        cols = [d[0] for d in cur.description]
        return [_import_row(cols, r) for r in cur.fetchall()]


def delete_import(import_id: str) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM imports WHERE import_id = ?", [import_id])
        con.execute("DELETE FROM import_links WHERE import_id = ?", [import_id])


def set_import_link(import_id: str, row_no: int, seg_ids: list[str], road_name: str | None) -> None:
    with db.connect() as con:
        con.execute("INSERT OR REPLACE INTO import_links VALUES (?, ?, ?, ?, ?)",
                    [import_id, row_no, seg_ids, road_name, _now()])


def clear_import_link(import_id: str, row_no: int) -> None:
    with db.connect() as con:
        con.execute("DELETE FROM import_links WHERE import_id = ? AND row_no = ?", [import_id, row_no])


def get_import_links(import_id: str) -> dict[int, dict]:
    with db.connect(read_only=True) as con:
        rows = con.execute("SELECT row_no, seg_ids, road_name FROM import_links WHERE import_id = ?",
                           [import_id]).fetchall()
    return {r[0]: {"seg_ids": list(r[1] or []), "road_name": r[2]} for r in rows}


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
