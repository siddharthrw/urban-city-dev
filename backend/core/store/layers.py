"""Read and write layer files (GeoParquet). Queries go through DuckDB, straight off the file,
so a layer never has to fit in memory.
"""
import json
import os
from pathlib import Path

import geopandas as gpd

from core.store import catalog, db


def write_geoparquet(gdf: gpd.GeoDataFrame, path: Path) -> None:
    """Write atomically: a crash mid-write never leaves a half-written layer behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    gdf.to_parquet(tmp, index=False, compression="zstd", write_covering_bbox=True)
    os.replace(tmp, path)


def _layer_file(city_id: str, layer_id: str) -> str:
    layer = catalog.get_layer(city_id, layer_id)
    if layer is None:
        raise LookupError(f"Layer '{layer_id}' has not been built for city '{city_id}'.")
    return str(layer["path"]).replace("\\", "/")


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
    city_id: str, layer_id: str, text_col: str, q: str, *, sum_col: str,
    label_cols: tuple[str, ...] = (), limit: int = 20,
) -> list[dict]:
    """Case-insensitive substring search, one row per distinct value of text_col,
    with feature count, summed column, bbox, and the most common value of each label column."""
    f = _layer_file(city_id, layer_id)
    labels = "".join(f", mode({c}) AS {c}" for c in label_cols)
    with db.connect_memory() as con:
        cur = con.execute(
            f"""
            SELECT {text_col} AS value, count(*) AS count, sum({sum_col}) AS total{labels},
                   [min(ST_XMin(geometry)), min(ST_YMin(geometry)),
                    max(ST_XMax(geometry)), max(ST_YMax(geometry))] AS bbox
            FROM read_parquet(?)
            WHERE {text_col} ILIKE '%' || ? || '%'
            GROUP BY {text_col}
            ORDER BY (lower({text_col}) LIKE lower(?) || '%') DESC, total DESC
            LIMIT ?
            """,
            [f, q, q, limit],
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
