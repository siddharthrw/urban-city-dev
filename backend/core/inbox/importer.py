"""Run an import: registered source file + target layer + confirmed mapping -> layer part.

Re-running the same (source, layer, sheet) replaces its previous result, so fixing a mapping or
linking a row by hand and importing again is always safe.
"""
import hashlib
from functools import lru_cache

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from core import modules
from core.inbox import files, readers, validate
from core.layers import registry
from core.store import catalog, db, layers

CITY_BBOX_MARGIN_DEG = 0.5  # lat/lon further than this outside the city's roads is suspicious


class ImportError_(ValueError):
    """Import can't run (bad mapping, unreadable file). Message is shown to the user."""


def import_id_for(source_id: str, layer_id: str, sheet: str | None) -> str:
    h = hashlib.sha1(f"{source_id}|{layer_id}|{sheet or ''}".encode()).hexdigest()[:10]
    return f"imp-{layer_id}-{h}"


@lru_cache(maxsize=1)
def _module_registry() -> tuple[dict, dict]:
    linkers, hooks = {}, {}
    for m in modules.discover():
        linkers.update(getattr(m, "IMPORT_LINKERS", {}))
        hooks.update(getattr(m, "IMPORT_HOOKS", {}))
    return linkers, hooks


def _city_bbox(city_id: str) -> tuple[float, float, float, float] | None:
    layer = catalog.get_layer(city_id, "roads")
    if layer is None:
        return None
    with db.connect_memory() as con:
        return con.execute(
            "SELECT min(ST_XMin(geometry)), min(ST_YMin(geometry)), max(ST_XMax(geometry)), max(ST_YMax(geometry)) "
            "FROM read_parquet(?)", [layer["path"].as_posix()]).fetchone()


def _place(clean: pd.DataFrame, table: pd.DataFrame, has_geometry: bool, crs: str | None,
           city_id: str, problems: list, warnings: list) -> gpd.GeoDataFrame:
    """Geometry for each clean row: the file's own, or latitude/longitude, or none (name only)."""
    if has_geometry:
        g = table.set_index(readers.ROW_NO).geometry
        if crs is None:
            raise ImportError_("This file has no coordinate system. Enter its EPSG code (e.g. 32644 for "
                               "UTM 44N) under options, or map a road-name column instead.")
        geoms = gpd.GeoSeries(g.loc[clean["row_no"]].values, crs=crs).to_crs(4326)
        return gpd.GeoDataFrame(clean, geometry=geoms.values, crs=4326)

    lat, lon = clean.get("latitude"), clean.get("longitude")
    geoms = [None] * len(clean)
    if lat is not None and lon is not None:
        bb = _city_bbox(city_id)
        swapped = 0
        for i, (y, x) in enumerate(zip(lat, lon)):
            if y is None or x is None or pd.isna(y) or pd.isna(x):
                continue
            if bb and not _inside(x, y, bb) and _inside(y, x, bb):
                x, y = y, x
                swapped += 1
            if bb and not _inside(x, y, bb):
                problems.append({"row_no": int(clean["row_no"].iloc[i]),
                                 "errors": [f"Location {y}, {x} is outside the city; ignored (check the columns)."]})
                continue
            geoms[i] = Point(float(x), float(y))
        if swapped:
            warnings.append(f"{swapped} rows had latitude and longitude swapped; corrected.")
    return gpd.GeoDataFrame(clean, geometry=gpd.GeoSeries(geoms, crs=4326).values, crs=4326)


def _inside(x, y, bb) -> bool:
    m = CITY_BBOX_MARGIN_DEG
    return bb[0] - m <= x <= bb[2] + m and bb[1] - m <= y <= bb[3] + m


def run_import(city_id: str, source_id: str, layer_id: str, mapping: dict[str, str],
               sheet: str | None = None, options: dict | None = None) -> dict:
    options = options or {}
    src = catalog.get_source(source_id)
    if src is None:
        raise ImportError_(f"Unknown source '{source_id}'.")
    ldef = registry.layer_def(layer_id)
    fields = registry.import_fields(layer_id)
    mapping = {f: c for f, c in mapping.items() if c}
    unknown = [f for f in mapping if f not in fields]
    if unknown:
        raise ImportError_(f"Unknown fields for {ldef['label']}: {', '.join(unknown)}")

    try:
        res = readers.read_file(src["abs_path"], sheet)
    except readers.UnsupportedFile as e:
        raise ImportError_(str(e)) from e
    missing_cols = [c for c in mapping.values() if c not in res.table.columns]
    if missing_cols:
        raise ImportError_(f"Columns not in the file: {', '.join(missing_cols)}")
    crs = res.crs or (f"EPSG:{int(options['epsg'])}" if options.get("epsg") else None)
    if not res.has_geometry and not ({"latitude", "longitude"} <= set(mapping) or "road_name" in mapping):
        raise ImportError_("Rows need a location: map Latitude + Longitude, or a Road name column.")
    missing_req = [fields[f].get("label", f) for f, s in fields.items() if s.get("required") and f not in mapping]
    if missing_req:
        raise ImportError_(f"Required field(s) not mapped: {', '.join(missing_req)}")

    warnings = list(res.warnings)
    clean, problems = validate.validate_rows(res.table, mapping, fields, readers.ROW_NO)
    n_problems = len(problems)
    gdf = _place(clean, res.table, res.has_geometry, crs, city_id, problems, warnings)
    bad_location = {p["row_no"] for p in problems[n_problems:]}  # lat/lon outside the city
    gdf = gdf[~gdf["row_no"].isin(bad_location)].reset_index(drop=True)

    iid = import_id_for(source_id, layer_id, res.sheet)
    sample = files.is_sample(src["name"])
    linkers, hooks = _module_registry()
    link_to = ldef.get("link_to")
    if link_to and link_to in linkers:
        links = linkers[link_to](city_id, gdf, gdf.get("road_name"), catalog.get_import_links(iid))
        for c in ("link_method", "seg_ids", "road_name_matched", "link_distance_m", "link_note"):
            gdf[c] = links[c].values
        use_road = gdf.geometry.isna() & links["road_geometry"].notna().values
        gdf.loc[use_road, "geometry"] = links.loc[use_road.values, "road_geometry"].values
    else:
        links = None
        gdf["seg_ids"] = [[] for _ in range(len(gdf))]

    unmatched = []
    if links is not None:
        for i in range(len(gdf)):
            if not gdf.at[i, "seg_ids"]:
                unmatched.append({
                    "row_no": int(gdf.at[i, "row_no"]),
                    "road_name": gdf.at[i, "road_name"] if "road_name" in gdf else None,
                    "reason": gdf.at[i, "link_note"],
                    "candidates": links.at[i, "candidates"] or [],
                    "has_location": links.at[i, "link_method"] == "location",
                })

    gdf.insert(0, "import_id", iid)
    gdf.insert(1, "source_id", source_id)
    gdf.insert(2, "city_id", city_id)
    gdf["is_sample"] = sample
    gdf["seg_id"] = [s[0] if s else None for s in gdf["seg_ids"]]
    gdf = gdf.set_geometry(gpd.GeoSeries(gdf.geometry, crs=4326))

    topic = ldef["topic"]
    part_dir = layers.write_partition(gdf, city_id, topic, layer_id, iid)
    _record(city_id, layer_id, topic, part_dir, extra_source=source_id)

    stats = {
        "rows_in_file": int(len(res.table)),
        "imported": int(len(gdf)),
        "invalid": len(problems),
        "linked": int(sum(1 for s in gdf["seg_ids"] if s)),
        "unmatched": len(unmatched),
        "on_map": int(gdf.geometry.notna().sum()),
        "by_link_method": {k: int(v) for k, v in pd.Series(gdf.get("link_method")).value_counts().items()} if len(gdf) else {},
        "is_sample": sample,
        "warnings": warnings,
    }
    hook = hooks.get(layer_id)
    if hook:
        stats["effects"] = hook(city_id, iid, gdf, src["name"])

    rec = {"import_id": iid, "city_id": city_id, "source_id": source_id, "layer_id": layer_id,
           "sheet": res.sheet, "mapping": mapping, "options": options, "status": "imported",
           "stats": stats, "problems": {"invalid": problems, "unmatched": unmatched}}
    catalog.save_import(rec)
    return rec


def _record(city_id: str, layer_id: str, topic: str, part_dir, extra_source: str | None = None) -> None:
    """(Re)record a partitioned layer: row count over all parts, sources of all its imports."""
    sources = {i["source_id"] for i in catalog.list_imports(city_id, layer_id)}
    if extra_source:
        sources.add(extra_source)
    catalog.record_layer(
        city_id=city_id, layer_id=layer_id, topic=topic, file=part_dir,
        geometry_type=registry.layer_def(layer_id).get("geometry_type", "Mixed"),
        feature_count=layers.count_rows(f"{part_dir.as_posix()}/*.parquet"),
        build_script="data inbox", source_ids=sorted(sources),
    )


def delete_import(import_id: str) -> dict:
    rec = catalog.get_import(import_id)
    if rec is None:
        raise ImportError_(f"No import '{import_id}'.")
    ldef = registry.layer_def(rec["layer_id"])
    left = layers.delete_partition(rec["city_id"], ldef["topic"], rec["layer_id"], import_id)
    catalog.delete_import(import_id)
    effects = None
    _, hooks = _module_registry()
    if rec["layer_id"] in hooks:
        effects = hooks[rec["layer_id"]](rec["city_id"], import_id, None, "")
    if left:
        _record(rec["city_id"], rec["layer_id"], ldef["topic"],
                layers.partition_dir(rec["city_id"], ldef["topic"], rec["layer_id"]))
    else:
        catalog.delete_layer_record(rec["city_id"], rec["layer_id"])
    return {"deleted": import_id, "effects": effects}
