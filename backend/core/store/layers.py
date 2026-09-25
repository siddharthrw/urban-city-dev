"""Read and write layer files (GeoParquet). Queries go through DuckDB, straight off the file,
so a layer never has to fit in memory.
"""
import json
import os
from pathlib import Path

import geopandas as gpd

from core.store import catalog, db, paths


def write_geoparquet(gdf: gpd.GeoDataFrame, path: Path) -> None:
    """Write atomically: a crash mid-write never leaves a half-written layer behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    gdf.to_parquet(tmp, index=False, compression="zstd", write_covering_bbox=True)
    os.replace(tmp, path)


def _layer_file(city_id: str, layer_id: str) -> str:
    """Path DuckDB should read: one file, or a glob over a partitioned layer's folder."""
    layer = catalog.get_layer(city_id, layer_id)
    if layer is None:
        raise LookupError(f"Layer '{layer_id}' has not been built for city '{city_id}'.")
    p = layer["path"]
    return (f"{p.as_posix()}/*.parquet" if p.is_dir() else p.as_posix())


# ---------- partitioned layers (one file per import) ----------

def partition_dir(city_id: str, topic: str, layer_id: str) -> Path:
    return paths.city_topic_dir(city_id, topic) / "layers" / layer_id


def write_partition(gdf: gpd.GeoDataFrame, city_id: str, topic: str, layer_id: str, part: str) -> Path:
    d = partition_dir(city_id, topic, layer_id)
    write_geoparquet(gdf, d / f"{part}.parquet")
    return d


def delete_partition(city_id: str, topic: str, layer_id: str, part: str) -> int:
    """Remove one part; returns how many parts are left."""
    d = partition_dir(city_id, topic, layer_id)
    (d / f"{part}.parquet").unlink(missing_ok=True)
    return len(list(d.glob("*.parquet"))) if d.exists() else 0


def count_rows(path_glob: str) -> int:
    with db.connect_memory() as con:
        return con.execute("SELECT count(*) FROM read_parquet(?)", [path_glob]).fetchone()[0]


def features_geojson(city_id: str, layer_id: str, bbox: tuple[float, float, float, float] | None,
                     limit: int = 5000, exclude: tuple[str, ...] = ()) -> dict:
    """GeoJSON FeatureCollection of a (small) layer, optionally cut to a map bbox."""
    f = _layer_file(city_id, layer_id)
    where = "geometry IS NOT NULL"
    params: list = [f]
    if bbox:
        where += (" AND ST_XMax(geometry) >= ? AND ST_XMin(geometry) <= ?"
                  " AND ST_YMax(geometry) >= ? AND ST_YMin(geometry) <= ?")
        params += [bbox[0], bbox[2], bbox[1], bbox[3]]
    with db.connect_memory() as con:
        excl = ", ".join(c for c in ("geometry", "bbox", *exclude) if c in _columns(con, f))
        cur = con.execute(
            f"SELECT * EXCLUDE ({excl}), ST_AsGeoJSON(geometry) AS __g FROM read_parquet(?, union_by_name=true) "
            f"WHERE {where} LIMIT ?", params + [limit + 1])
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    feats = []
    for r in rows[:limit]:
        props = dict(zip(cols, r))
        geom = json.loads(props.pop("__g"))
        feats.append({"type": "Feature", "geometry": geom, "properties": _jsonable(props)})
    return {"type": "FeatureCollection", "features": feats, "truncated": len(rows) > limit}


def rows_linked_to(city_id: str, layer_id: str, seg_id: str, limit: int = 20) -> list[dict]:
    """Rows of an imported layer linked to a road segment (seg_ids list contains it)."""
    f = _layer_file(city_id, layer_id)
    with db.connect_memory() as con:
        excl = ", ".join(c for c in ("geometry", "bbox") if c in _columns(con, f))
        cur = con.execute(
            f"SELECT * EXCLUDE ({excl}) FROM read_parquet(?, union_by_name=true) "
            "WHERE list_contains(seg_ids, ?) LIMIT ?", [f, seg_id, limit])
        cols = [d[0] for d in cur.description]
        return [_jsonable(dict(zip(cols, r))) for r in cur.fetchall()]


def _columns(con, f: str) -> list[str]:
    return [r[0] for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?, union_by_name=true)", [f]).fetchall()]


def _jsonable(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if hasattr(v, "isoformat"):
            v = v.isoformat()
        elif isinstance(v, float) and v != v:  # NaN
            v = None
        out[k] = v
    return out


def get_feature(city_id: str, layer_id: str, key_col: str, key: str) -> dict | None:
    """One feature as a dict of attributes, plus its GeoJSON geometry and bbox."""
    f = _layer_file(city_id, layer_id)
    with db.connect_memory() as con:
        cur = con.execute(
            f"""
            SELECT * EXCLUDE (geometry, bbox),
                   ST_AsGeoJSON(geometry) AS geometry_geojson,
                   [ST_XMin(geometry), ST_YMin(geometry), ST_XMax(geometry), ST_YMax(geometry)] AS bbox
            FROM read_parquet(?) WHERE {key_col} = ?
            """,
            [f, key],
        )
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
    out = dict(zip(cols, row))
    out["geometry"] = json.loads(out.pop("geometry_geojson"))
    return out


def group_stats(city_id: str, layer_id: str, group_col: str, value: str, sum_col: str) -> dict:
    """Count, summed column and bbox for all features sharing one value (e.g. all segments of a named road)."""
    f = _layer_file(city_id, layer_id)
    with db.connect_memory() as con:
        row = con.execute(
            f"""
            SELECT count(*), sum({sum_col}),
                   min(ST_XMin(geometry)), min(ST_YMin(geometry)),
                   max(ST_XMax(geometry)), max(ST_YMax(geometry))
            FROM read_parquet(?) WHERE {group_col} = ?
            """,
            [f, value],
        ).fetchone()
    return {"count": row[0], "sum": row[1], "bbox": list(row[2:6])}


def search_text(
    city_id: str, layer_id: str, group_col: str, pattern: str, *, match_col: str, sum_col: str,
    label_cols: tuple[str, ...] = (), limit: int = 20,
) -> list[dict]:
    """Substring search on match_col (case-insensitive), one row per distinct group_col value,
    with feature count, summed column, bbox, and the most common value of each label column.
    Results that start with the pattern come first, then the biggest."""
    f = _layer_file(city_id, layer_id)
    labels = "".join(f", mode({c}) AS {c}" for c in label_cols)
    with db.connect_memory() as con:
        cur = con.execute(
            f"""
            SELECT {group_col} AS value, count(*) AS count, sum({sum_col}) AS total{labels},
                   [min(ST_XMin(geometry)), min(ST_YMin(geometry)),
                    max(ST_XMax(geometry)), max(ST_YMax(geometry))] AS bbox
            FROM read_parquet(?)
            WHERE {match_col} ILIKE '%' || ? || '%' AND {group_col} IS NOT NULL
            GROUP BY {group_col}
            ORDER BY bool_or({match_col} ILIKE ? || '%' OR {match_col} ILIKE '%| ' || ? || '%') DESC, total DESC
            LIMIT ?
            """,
            [f, pattern, pattern, pattern, limit],
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
