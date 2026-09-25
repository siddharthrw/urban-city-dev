"""Read any supported partner file into a table.

Tabular files (CSV, Excel) come back as a DataFrame of strings/objects with the header row found
automatically (government sheets often start with a title or blank rows). GIS files (KML/KMZ,
GeoJSON, shapefile, GeoPackage, DXF) come back as a GeoDataFrame.

Every row gets `_row_no`: the row number a person would see when opening the file (spreadsheet row,
or feature number for GIS files), so problems can be reported back in their terms.
"""
import csv
import html
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio

ROW_NO = "_row_no"
TABULAR = {".csv", ".txt", ".tsv", ".xlsx", ".xlsm"}
GIS = {".kml", ".kmz", ".geojson", ".json", ".gpkg", ".shp", ".zip", ".dxf"}
STORED_ONLY = {".pdf", ".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff", ".doc", ".docx",
               ".ppt", ".pptx", ".xls", ".dwg"}
# Columns KML/GDAL adds that carry no information for us.
KML_NOISE = {"id", "timestamp", "begin", "end", "altitudeMode", "tessellate", "extrude",
             "visibility", "drawOrder", "icon", "snippet", "styleUrl"}


class UnsupportedFile(ValueError):
    pass


@dataclass
class ReadResult:
    table: pd.DataFrame  # GeoDataFrame for GIS files
    has_geometry: bool
    crs: str | None = None
    sheets: list[str] | None = None
    sheet: str | None = None
    header_row: int | None = None  # 1-based, tabular only
    warnings: list[str] = field(default_factory=list)


def kind_of(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in TABULAR:
        return "table"
    if ext in GIS:
        return "gis"
    if ext in STORED_ONLY:
        return "stored_only"
    return "unknown"


def read_file(path: Path, sheet: str | None = None) -> ReadResult:
    ext = path.suffix.lower()
    if ext in (".csv", ".txt", ".tsv"):
        return _read_csv(path)
    if ext in (".xlsx", ".xlsm"):
        return _read_excel(path, sheet)
    if ext in GIS:
        return _read_gis(path)
    if ext == ".xls":
        raise UnsupportedFile("Old .xls format: open it in Excel and save as .xlsx, then import that.")
    if ext == ".dwg":
        raise UnsupportedFile("AutoCAD .dwg can't be read directly: export it from AutoCAD as .dxf.")
    if ext in STORED_ONLY:
        raise UnsupportedFile(
            f"{ext} files are stored and registered, but automatic import (PDF tables, photo locations) "
            "is not built yet. Type the numbers into a CSV/Excel sheet for now.")
    raise UnsupportedFile(f"Don't know how to read '{ext}' files.")


# ---------- tabular ----------

def _find_header(raw: pd.DataFrame, max_scan: int = 15) -> int:
    """Index of the header row: the first row (of the first few) that is mostly filled with
    text labels, as full as the widest row of the table."""
    widest = int(raw.notna().sum(axis=1).max()) if len(raw) else 0
    for i in range(min(max_scan, len(raw))):
        row = raw.iloc[i]
        vals = [v for v in row if pd.notna(v) and str(v).strip() != ""]
        if len(vals) < max(2, 0.6 * widest):
            continue
        texty = sum(1 for v in vals if not _looks_numeric(v))
        if texty >= 0.8 * len(vals):
            return i
    return 0


def _looks_numeric(v) -> bool:
    if isinstance(v, (int, float)):
        return True
    try:
        float(str(v).replace(",", "").strip())
        return True
    except ValueError:
        return False


def _unique_headers(values) -> list[str]:
    out, seen = [], {}
    for i, v in enumerate(values):
        h = str(v).strip() if pd.notna(v) and str(v).strip() else f"column_{i + 1}"
        h = re.sub(r"\s+", " ", h)
        if h in seen:
            seen[h] += 1
            h = f"{h} ({seen[h]})"
        else:
            seen[h] = 1
        out.append(h)
    return out


def _tabulate(raw: pd.DataFrame, first_line_no: int = 1) -> tuple[pd.DataFrame, int]:
    raw = raw.dropna(axis=1, how="all")
    h = _find_header(raw)
    df = raw.iloc[h + 1:].copy()
    df.columns = _unique_headers(raw.iloc[h].tolist())
    # Spreadsheet row number: header is at line first_line_no + h.
    df.insert(0, ROW_NO, [first_line_no + h + 1 + i for i in range(len(df))])
    df = df.dropna(how="all", subset=[c for c in df.columns if c != ROW_NO])
    df = df.map(lambda v: v.strip() if isinstance(v, str) else v).reset_index(drop=True)
    return df, first_line_no + h


def _read_csv(path: Path) -> ReadResult:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        sep = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|").delimiter
    except csv.Error:
        sep = ","
    raw = pd.read_csv(io.StringIO(text), sep=sep, header=None, dtype=str, keep_default_na=False,
                      na_values=[""], skip_blank_lines=False, engine="python")
    df, header = _tabulate(raw)
    warnings = [] if enc == "utf-8-sig" else [f"File is not UTF-8; read as {enc}."]
    return ReadResult(df, has_geometry=False, header_row=header, warnings=warnings)


def _read_excel(path: Path, sheet: str | None) -> ReadResult:
    xl = pd.ExcelFile(path, engine="openpyxl")
    sheets = xl.sheet_names
    name = sheet if sheet is not None else sheets[0]
    if name not in sheets:
        raise UnsupportedFile(f"No sheet '{name}' in this workbook (sheets: {', '.join(sheets)}).")
    raw = xl.parse(name, header=None, dtype=object)
    df, header = _tabulate(raw)
    warnings = [f"Workbook has {len(sheets)} sheets; reading '{name}'."] if len(sheets) > 1 else []
    return ReadResult(df, has_geometry=False, sheets=sheets, sheet=name, header_row=header, warnings=warnings)


# ---------- GIS ----------

def _html_table_pairs(desc: str) -> dict:
    """ArcGIS-style KML puts attributes in an HTML table inside <description>: pull key/value pairs."""
    cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", desc or "", flags=re.S | re.I)
    cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in cells]
    return {cells[i]: cells[i + 1] for i in range(0, len(cells) - 1, 2) if cells[i]}


def _read_gis(path: Path) -> ReadResult:
    ext = path.suffix.lower()
    warnings: list[str] = []
    target = str(path)
    if ext == ".zip":
        with zipfile.ZipFile(path) as z:
            shp = [n for n in z.namelist() if n.lower().endswith((".shp", ".gpkg", ".geojson", ".kml"))]
        if not shp:
            raise UnsupportedFile("Zip file has no .shp / .gpkg / .geojson / .kml inside.")
        target = f"/vsizip/{path.as_posix()}/{shp[0]}"
        if len(shp) > 1:
            warnings.append(f"Zip has {len(shp)} GIS files; reading '{shp[0]}'.")

    layers = [row[0] for row in pyogrio.list_layers(target)]
    parts = []
    for lyr in layers:
        g = gpd.read_file(target, layer=lyr)
        if len(g) == 0:
            continue
        if len(layers) > 1:
            g["source_layer"] = lyr
        parts.append(g)
    if not parts:
        raise UnsupportedFile("The file has no features.")
    g = pd.concat(parts, ignore_index=True) if len(parts) > 1 else parts[0]
    g = gpd.GeoDataFrame(g, geometry="geometry", crs=parts[0].crs)

    if ext in (".kml", ".kmz") or "kml" in target.lower():
        drop = [c for c in g.columns if c in KML_NOISE]
        g = g.drop(columns=drop)
        if "description" in g.columns and g["description"].astype(str).str.contains("<td", case=False).any():
            extra = pd.DataFrame([_html_table_pairs(d) for d in g["description"].fillna("")])
            extra = extra[[c for c in extra.columns if c not in g.columns]]
            g = pd.concat([g.drop(columns=["description"]), extra], axis=1)
            g = gpd.GeoDataFrame(g, geometry="geometry", crs=parts[0].crs)
            warnings.append("Attributes were read from the HTML table in each placemark's description.")
        for c in ("Name", "description"):
            if c in g.columns and g[c].isna().all():
                g = g.drop(columns=[c])

    crs = g.crs.to_string() if g.crs else None
    if crs is None:
        warnings.append("File has no coordinate system (common for AutoCAD). "
                        "Tell the import which EPSG code it uses, or match rows by road name instead.")
    g.insert(0, ROW_NO, range(1, len(g) + 1))
    g = g[[c for c in g.columns if c != "geometry"] + ["geometry"]]
    return ReadResult(g, has_geometry=True, crs=crs, warnings=warnings)


def preview(result: ReadResult, n: int = 10) -> dict:
    """What the mapping screen shows: columns with inferred types, a few rows, row count."""
    t = result.table
    cols = [c for c in t.columns if c not in (ROW_NO, "geometry")]
    info = []
    for c in cols:
        s = t[c].dropna()
        s = s[s.astype(str).str.strip() != ""]
        info.append({"name": c, "type": infer_type(s), "filled": int(len(s))})
    rows = t[[ROW_NO] + cols].head(n).astype(object).where(t[[ROW_NO] + cols].head(n).notna(), None)
    geom = None
    if result.has_geometry:
        geom = {"types": t.geometry.geom_type.value_counts().to_dict(), "crs": result.crs,
                "empty": int(t.geometry.is_empty.sum() + t.geometry.isna().sum())}
    return {
        "columns": info,
        "rows": [{k: (str(v) if v is not None else None) for k, v in r.items()} for r in rows.to_dict("records")],
        "row_count": int(len(t)),
        "has_geometry": result.has_geometry,
        "geometry": geom,
        "sheets": result.sheets,
        "sheet": result.sheet,
        "header_row": result.header_row,
        "warnings": result.warnings,
    }


def infer_type(values: pd.Series) -> str:
    """number | date | text | empty, from a sample of non-blank values."""
    if len(values) == 0:
        return "empty"
    sample = values.head(200)
    if sum(_looks_numeric(v) for v in sample) >= 0.9 * len(sample):
        return "number"
    if pd.api.types.is_datetime64_any_dtype(values) or all(hasattr(v, "year") for v in sample):
        return "date"
    parsed = pd.to_datetime(sample.astype(str), errors="coerce", dayfirst=True, format="mixed")
    if parsed.notna().mean() >= 0.9:
        return "date"
    return "text"
