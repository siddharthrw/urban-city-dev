"""GeoParquet -> PMTiles vector tiles, generated locally with DuckDB's ST_AsMVT.

Pure Python (no tippecanoe, which doesn't run natively on Windows). One SQL query per zoom
level cuts every feature into every tile it touches; the pmtiles writer packs them into one
file the map reads with HTTP range requests.
"""
import gzip
import os
from pathlib import Path

from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer

from core.store import db

EXTENT = 4096


def build_pmtiles(
    *, parquet: Path, out: Path, layer_name: str, properties: list[str],
    minzoom: int, maxzoom: int, zoom_filter: dict[int, str] | None = None,
) -> dict:
    """Build a PMTiles file from a GeoParquet layer (EPSG:4326).

    zoom_filter: optional {zoom: SQL WHERE clause}; the clause for the highest zoom <= z applies,
    so low zooms can carry only major features.
    """
    src = str(parquet).replace("\\", "/")
    props = ", ".join(f"'{p}': {p}" for p in properties)
    zoom_filter = zoom_filter or {}
    tiles: dict[int, bytes] = {}

    with db.connect_memory() as con:
        con.execute(
            f"""
            CREATE TEMP TABLE feats AS
            SELECT {", ".join(properties)},
                   ST_Transform(geometry, 'EPSG:4326', 'EPSG:3857', always_xy := true) AS g3857,
                   ST_XMin(geometry) AS xmin, ST_YMin(geometry) AS ymin,
                   ST_XMax(geometry) AS xmax, ST_YMax(geometry) AS ymax
            FROM read_parquet('{src}')
            """
        )
        lon0, lat0, lon1, lat1 = con.execute(
            "SELECT min(xmin), min(ymin), max(xmax), max(ymax) FROM feats"
        ).fetchone()

        for z in range(minzoom, maxzoom + 1):
            applicable = [k for k in zoom_filter if k <= z]
            where = zoom_filter[max(applicable)] if applicable else "TRUE"
            n = 2**z
            # Each feature's tile range from its bbox; then clip + encode per tile.
            rows = con.execute(
                f"""
                WITH f AS (
                    SELECT *,
                        floor((xmin + 180) / 360 * {n})::INT AS tx0,
                        floor((xmax + 180) / 360 * {n})::INT AS tx1,
                        floor((1 - asinh(tan(radians(ymax))) / pi()) / 2 * {n})::INT AS ty0,
                        floor((1 - asinh(tan(radians(ymin))) / pi()) / 2 * {n})::INT AS ty1
                    FROM feats WHERE {where}
                ),
                ft AS (
                    SELECT f.*, tx.x::INTEGER AS x, ty.y::INTEGER AS y
                    FROM f,
                         LATERAL (SELECT unnest(range(f.tx0, f.tx1 + 1)) AS x) tx,
                         LATERAL (SELECT unnest(range(f.ty0, f.ty1 + 1)) AS y) ty
                ),
                clipped AS (
                    SELECT x, y, {", ".join(properties)},
                           ST_AsMVTGeom(g3857, ST_Extent(ST_TileEnvelope({z}, x, y)), {EXTENT}, 64, true) AS geom
                    FROM ft
                )
                SELECT x, y, ST_AsMVT({{{props}, 'geom': geom}}, '{layer_name}', {EXTENT}, 'geom')
                FROM clipped WHERE geom IS NOT NULL AND NOT ST_IsEmpty(geom)
                GROUP BY x, y
                """
            ).fetchall()
            for x, y, blob in rows:
                if blob:
                    tiles[zxy_to_tileid(z, x, y)] = gzip.compress(bytes(blob))

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".pmtiles.tmp")
    with open(tmp, "wb") as f:
        w = Writer(f)
        for tid in sorted(tiles):
            w.write_tile(tid, tiles[tid])
        w.finalize(
            {
                "tile_type": TileType.MVT,
                "tile_compression": Compression.GZIP,
                "min_zoom": minzoom,
                "max_zoom": maxzoom,
                "min_lon_e7": int(lon0 * 1e7), "min_lat_e7": int(lat0 * 1e7),
                "max_lon_e7": int(lon1 * 1e7), "max_lat_e7": int(lat1 * 1e7),
                "center_zoom": minzoom,
                "center_lon_e7": int((lon0 + lon1) / 2 * 1e7),
                "center_lat_e7": int((lat0 + lat1) / 2 * 1e7),
            },
            {
                "vector_layers": [
                    {"id": layer_name, "fields": {p: "String" for p in properties},
                     "minzoom": minzoom, "maxzoom": maxzoom}
                ]
            },
        )
    os.replace(tmp, out)
    return {"tiles": len(tiles), "bytes": out.stat().st_size}
