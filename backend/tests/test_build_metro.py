"""Metro stations build: the station list is read and checked before a layer is written."""
import geopandas as gpd
import pytest
from shapely.geometry import Point

from scripts.build_metro import load_stations, validate_stations

HEADER = "station_name,line,lat,lon,coordinate_source\n"


def _write_list(tmp_path, rows: str):
    path = tmp_path / "stations.csv"
    path.write_text(HEADER + rows, encoding="utf-8")
    return path


def _gdf(rows):
    return gpd.GeoDataFrame(
        [{"station_name": n, "line": ln, "geometry": Point(lon, lat)} for n, ln, lat, lon in rows],
        geometry="geometry", crs="EPSG:4326")


def test_csv_loads_names_lines_and_points(tmp_path):
    path = _write_list(tmp_path, "AGDMS,Blue,13.04587,80.24828,OSM: AGTMS\nEgmore,Green,13.08028,80.26305,OSM: Egmore\n")
    stations = load_stations(path)
    assert list(stations["station_name"]) == ["AGDMS", "Egmore"]
    assert stations.iloc[0].geometry.x == pytest.approx(80.24828)
    assert stations.crs == "EPSG:4326"


def test_a_good_list_passes():
    validate_stations(_gdf([("Guindy", "Blue", 13.00927, 80.21308), ("Egmore", "Green", 13.08028, 80.26305)]))


def test_duplicate_names_stop_the_build():
    with pytest.raises(ValueError, match="duplicate"):
        validate_stations(_gdf([("Alandur", "Blue", 13.0, 80.2), ("Alandur", "Green", 13.0, 80.2)]))


def test_a_point_outside_chennai_stops_the_build():
    with pytest.raises(ValueError, match="outside Greater Chennai"):
        validate_stations(_gdf([("Madurai", "Blue", 9.9, 78.1)]))


def test_an_unknown_line_stops_the_build():
    with pytest.raises(ValueError, match="unknown line"):
        validate_stations(_gdf([("Guindy", "Purple", 13.0, 80.2)]))


def test_an_empty_list_stops_the_build():
    with pytest.raises(ValueError, match="empty"):
        validate_stations(gpd.GeoDataFrame({"station_name": [], "line": []}, geometry=[], crs="EPSG:4326"))
