"""Sample-and-vote matching, in a local metric grid (metres)."""
import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon

from core import geo

CRS = "EPSG:32644"
X0, Y0 = 400000, 1440000  # somewhere in Chennai's UTM zone


def lines(coords_list, **cols):
    return gpd.GeoDataFrame(cols, geometry=[LineString([(X0 + a, Y0 + b) for a, b in c]) for c in coords_list], crs=CRS)


# A horizontal street (h) crossed at x=100 by a vertical street (v).
TARGETS = lines([[(0, 0), (200, 0)], [(100, -100), (100, 100)]], tid=["h", "v"])


def test_best_line_match_prefers_the_street_running_along():
    src = lines([[(20, 2), (180, 2)],      # runs along h, 2 m off
                 [(98, -80), (98, 80)],    # runs along v
                 [(0, 50), (200, 50)]])    # 50 m away from h: no match
    m = geo.best_line_match(src.geometry, TARGETS, "tid", max_dist_m=8)
    got = dict(zip(m["src"], m["tid"]))
    assert got == {0: "h", 1: "v"}
    # 4 of 5 samples vote h; the one exactly at the junction (x=100) sits on v.
    assert m.loc[m["src"] == 0, "share"].iloc[0] == 0.8


def test_short_segment_at_a_junction_is_not_named_by_the_crossing_street():
    # 30 m piece of h that ends at the junction with v.
    src = lines([[(70, 0), (100, 0)]])
    m = geo.best_line_match(src.geometry, TARGETS, "tid", max_dist_m=8)
    assert m["tid"].tolist() == ["h"]


def test_lines_to_segments_collects_every_segment_along():
    segs = lines([[(0, 0), (100, 0)], [(100, 0), (200, 0)], [(200, 0), (300, 0)], [(100, 0), (100, 100)]],
                 seg_id=["a", "b", "c", "x"])
    src = lines([[(10, 1), (290, 1)]])
    m = geo.lines_to_segments(src.geometry, segs, "seg_id")
    assert set(m["seg_ids"].iloc[0]) == {"a", "b", "c"}  # not the crossing street x


def test_points_to_segments_respects_max_distance():
    segs = lines([[(0, 0), (100, 0)]], seg_id=["a"])
    pts = gpd.GeoSeries([Point(X0 + 50, Y0 + 10), Point(X0 + 50, Y0 + 80)], crs=CRS)
    m = geo.points_to_segments(pts, segs, "seg_id", max_dist_m=30)
    assert m["src"].tolist() == [0] and m["seg_id"].tolist() == ["a"]
    assert abs(m["distance_m"].iloc[0] - 10) < 1e-6


def test_polygons_to_segments():
    segs = lines([[(0, 0), (100, 0)], [(0, 500), (100, 500)]], seg_id=["in", "out"])
    poly = gpd.GeoSeries([Polygon([(X0 + 20, Y0 - 20), (X0 + 60, Y0 - 20), (X0 + 60, Y0 + 20), (X0 + 20, Y0 + 20)])], crs=CRS)
    m = geo.polygons_to_segments(poly, segs, "seg_id")
    assert m["seg_ids"].iloc[0] == ["in"]
