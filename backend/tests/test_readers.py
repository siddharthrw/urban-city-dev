"""Every supported format, plus the messy-spreadsheet cases partners actually send."""
import json
import zipfile

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString, Point

from core.inbox import readers
from tests.conftest import SAMPLES

ROW = readers.ROW_NO


def test_csv_with_title_rows_finds_header_and_spreadsheet_row_numbers():
    r = readers.read_file(SAMPLES / "SAMPLE_traffic_counts.csv")
    assert r.header_row == 3
    assert list(r.table.columns[:4]) == [ROW, "Sl No", "Road Name", "Date"]
    assert r.table.iloc[0][ROW] == 4 and r.table.iloc[0]["Road Name"] == "North Usman Road"
    assert len(r.table) == 12 and not r.has_geometry


def test_csv_semicolons_and_windows_encoding(tmp_path):
    p = tmp_path / "counts.csv"
    p.write_bytes("Road;Cars\nCaf\xe9 Street;10\n".encode("cp1252"))
    r = readers.read_file(p)
    assert r.table.iloc[0]["Road"] == "Café Street" and r.table.iloc[0]["Cars"] == "10"
    assert any("cp1252" in w for w in r.warnings)


def test_csv_duplicate_and_blank_headers(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("Road,Count,Count,\nA,1,2,x\n", encoding="utf-8")
    cols = list(readers.read_file(p).table.columns)
    assert cols == [ROW, "Road", "Count", "Count (2)", "column_4"]


def test_excel_sheets_and_header_detection(tmp_path):
    p = tmp_path / "survey.xlsx"
    with pd.ExcelWriter(p) as w:
        pd.DataFrame([["GCC road survey 2026", None], [None, None], ["Road Name", "ROW (m)"], ["Anna Salai", 30]]).to_excel(
            w, sheet_name="Widths", header=False, index=False)
        pd.DataFrame({"a": [1]}).to_excel(w, sheet_name="Notes", index=False)
    r = readers.read_file(p)
    assert r.sheets == ["Widths", "Notes"] and r.sheet == "Widths" and r.header_row == 3
    assert r.table.iloc[0]["Road Name"] == "Anna Salai" and r.table.iloc[0][ROW] == 4
    assert readers.read_file(p, "Notes").table.iloc[0]["a"] == 1
    with pytest.raises(readers.UnsupportedFile):
        readers.read_file(p, "Missing")


def test_kml_extended_data():
    r = readers.read_file(SAMPLES / "SAMPLE_bus_stops.kml")
    assert r.has_geometry and r.crs and "4326" in r.crs
    t = r.table
    assert {"stop_name", "routes", "daily_boardings"} <= set(t.columns)
    assert not ({"altitudeMode", "tessellate"} & set(t.columns))  # KML noise dropped
    assert t[ROW].tolist() == [1, 2, 3, 4, 5]


def test_kml_attributes_in_html_description(tmp_path):
    p = tmp_path / "arc.kml"
    p.write_text("""<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark>
      <name>P1</name><description><![CDATA[<table><tr><td>ROAD_NAME</td><td>Anna Salai</td></tr>
      <tr><td>WIDTH</td><td>30</td></tr></table>]]></description>
      <Point><coordinates>80.25,13.06</coordinates></Point></Placemark></Document></kml>""", encoding="utf-8")
    r = readers.read_file(p)
    assert r.table.iloc[0]["ROAD_NAME"] == "Anna Salai" and r.table.iloc[0]["WIDTH"] == "30"
    assert "description" not in r.table.columns


def test_kmz(tmp_path):
    p = tmp_path / "stops.kmz"
    with zipfile.ZipFile(p, "w") as z:
        z.write(SAMPLES / "SAMPLE_bus_stops.kml", "doc.kml")
    assert len(readers.read_file(p).table) == 5


def _gdf():
    return gpd.GeoDataFrame({"name": ["A", "B"], "width": [10.0, 12.0]},
                            geometry=[LineString([(80.25, 13.06), (80.26, 13.06)]), Point(80.25, 13.07)], crs=4326)


def test_geojson_and_geopackage(tmp_path):
    g = _gdf()
    g.to_file(tmp_path / "x.geojson", driver="GeoJSON")
    g.to_file(tmp_path / "x.gpkg", driver="GPKG")
    for f in ("x.geojson", "x.gpkg"):
        r = readers.read_file(tmp_path / f)
        assert r.has_geometry and len(r.table) == 2 and r.table.iloc[0]["name"] == "A"


def test_zipped_shapefile(tmp_path):
    g = _gdf().iloc[[1]]
    shp_dir = tmp_path / "shp"
    shp_dir.mkdir()
    g.to_file(shp_dir / "stops.shp")
    z = tmp_path / "stops.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in shp_dir.iterdir():
            zf.write(f, f.name)
    r = readers.read_file(z)
    assert len(r.table) == 1 and r.table.iloc[0]["name"] == "B" and r.crs


def test_dxf_has_no_crs_and_says_so(tmp_path):
    g = gpd.GeoDataFrame({"Layer": ["ROAD"]}, geometry=[LineString([(0, 0), (100, 0)])])
    g.to_file(tmp_path / "plan.dxf", driver="DXF")
    r = readers.read_file(tmp_path / "plan.dxf")
    assert r.has_geometry and r.crs is None
    assert any("coordinate system" in w for w in r.warnings)


@pytest.mark.parametrize("name, msg", [
    ("scan.pdf", "not built yet"), ("photo.jpg", "not built yet"), ("old.xls", "save as .xlsx"),
    ("plan.dwg", ".dxf"), ("data.xyz", "Don't know"),
])
def test_unsupported(tmp_path, name, msg):
    p = tmp_path / name
    p.write_bytes(b"x")
    with pytest.raises(readers.UnsupportedFile, match=msg):
        readers.read_file(p)


def test_kind_of():
    assert readers.kind_of(SAMPLES / "a.csv") == "table"
    assert readers.kind_of(SAMPLES / "a.KML") == "gis"
    assert readers.kind_of(SAMPLES / "a.pdf") == "stored_only"


def test_infer_type():
    assert readers.infer_type(pd.Series(["1", "2,000", "3.5"])) == "number"
    assert readers.infer_type(pd.Series(["12/08/2026", "13/08/2026"])) == "date"
    assert readers.infer_type(pd.Series(["Anna Salai", "12"])) == "text"
    assert readers.infer_type(pd.Series([], dtype=object)) == "empty"


def test_preview_shape():
    p = readers.preview(readers.read_file(SAMPLES / "SAMPLE_traffic_counts.csv"), n=3)
    assert p["row_count"] == 12 and len(p["rows"]) == 3 and p["header_row"] == 3
    types = {c["name"]: c["type"] for c in p["columns"]}
    assert types["Cars"] == "number" and types["Date"] == "date" and types["Road Name"] == "text"
    json.dumps(p)  # must be JSON-serialisable for the API
