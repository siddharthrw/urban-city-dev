"""Tests for the building-footprint width measurement module and the verify-width endpoint."""
import json

import numpy as np
import pytest
from shapely import STRtree
from shapely.geometry import Polygon, LineString, Point

from modules.roads.pipelines.measure_widths import (
    _ray_min_dist,
    _sample_segment,
    measure_segment,
    MIN_SAMPLES,
)


# ---------- geometry helpers ----------

def _make_tree(polygons: list) -> tuple[STRtree, list]:
    tree = STRtree(polygons)
    return tree, polygons


# ---------- _sample_segment ----------

def test_sample_segment_short_line_gives_midpoint():
    line = LineString([(0, 0), (5, 0)])  # 5 m, shorter than STEP_M (15 m)
    samples = _sample_segment(line, step=15)
    assert len(samples) == 1
    pt, dx, dy = samples[0]
    # The midpoint of a horizontal line is at x=2.5
    assert abs(pt.x - 2.5) < 0.5


def test_sample_segment_long_line_gives_multiple_samples():
    line = LineString([(0, 0), (100, 0)])  # 100 m, step 15 m -> ~6 samples
    samples = _sample_segment(line, step=15)
    assert len(samples) >= 5


def test_sample_segment_perpendicular_is_correct():
    """For a horizontal road going east (+x), the perpendicular-right should be south (-y)."""
    line = LineString([(0, 0), (50, 0)])  # eastward road
    samples = _sample_segment(line, step=15)
    for _, dx, dy in samples:
        # Right perp of eastward road should be (0, -1) in (east, north) = (dx, dy)
        assert abs(dx) < 0.01  # no east component in right perp
        assert dy < -0.9       # strong south component


def test_sample_segment_empty_for_tiny_line():
    line = LineString([(0, 0), (0.001, 0)])  # < 1 m
    assert _sample_segment(line, step=15) == []


# ---------- _ray_min_dist ----------

def test_ray_hits_building_in_front():
    """Ray going east; building at x=10."""
    origin = Point(0, 0)
    ray = LineString([(0, 0), (20, 0)])  # eastward ray, 20 m long
    building = Polygon([(9, -1), (11, -1), (11, 1), (9, 1)])  # 2 m wide at x=9-11
    tree, geoms = _make_tree([building])
    d = _ray_min_dist(origin, ray, [0], geoms)
    assert d is not None
    assert abs(d - 9.0) < 0.1


def test_ray_misses_building_behind():
    """Ray going east; building is to the west — should not intersect."""
    origin = Point(0, 0)
    ray = LineString([(0, 0), (20, 0)])
    building = Polygon([(-5, -1), (-3, -1), (-3, 1), (-5, 1)])
    tree, geoms = _make_tree([building])
    assert _ray_min_dist(origin, ray, [0], geoms) is None


def test_ray_no_candidates_returns_none():
    origin = Point(0, 0)
    ray = LineString([(0, 0), (20, 0)])
    assert _ray_min_dist(origin, ray, [], []) is None


def test_ray_returns_nearest_of_two_buildings():
    """Ray going east; two buildings at x=8 and x=15."""
    origin = Point(0, 0)
    ray = LineString([(0, 0), (20, 0)])
    b1 = Polygon([(7, -1), (9, -1), (9, 1), (7, 1)])   # x=7-9
    b2 = Polygon([(14, -1), (16, -1), (16, 1), (14, 1)])  # x=14-16
    tree, geoms = _make_tree([b1, b2])
    d = _ray_min_dist(origin, ray, [0, 1], geoms)
    assert d is not None
    assert abs(d - 7.0) < 0.1  # nearest is b1 at x=7


# ---------- measure_segment ----------

def _road_with_buildings(road_half_width: float, segment_length: float = 100):
    """Creates a horizontal road segment with buildings on both sides at the given half-width."""
    line = LineString([(0, 0), (segment_length, 0)])
    # Buildings: strip running along the road at ±road_half_width
    right_building = Polygon([
        (0, road_half_width), (segment_length, road_half_width),
        (segment_length, road_half_width + 5), (0, road_half_width + 5),
    ])
    left_building = Polygon([
        (0, -road_half_width - 5), (segment_length, -road_half_width - 5),
        (segment_length, -road_half_width), (0, -road_half_width),
    ])
    tree, geoms = _make_tree([right_building, left_building])
    return line, tree, geoms


def test_measure_segment_known_width():
    """A 18 m wide road (9 m each side) should measure close to 18 m."""
    line, tree, geoms = _road_with_buildings(9.0)
    result = measure_segment(line, tree, geoms)
    assert result is not None
    assert abs(result["width_m"] - 18.0) < 1.0


def test_measure_segment_returns_sample_counts():
    line, tree, geoms = _road_with_buildings(6.0)
    result = measure_segment(line, tree, geoms)
    assert result is not None
    assert result["valid_samples"] >= MIN_SAMPLES
    assert result["total_samples"] >= result["valid_samples"]


def test_measure_segment_no_buildings_returns_none():
    line = LineString([(0, 0), (100, 0)])
    tree, geoms = _make_tree([])
    assert measure_segment(line, tree, geoms) is None


def test_measure_segment_too_short_returns_none():
    """A very short segment (< step size) that still gets sampled but has no buildings."""
    line = LineString([(0, 0), (10, 0)])
    tree, geoms = _make_tree([])
    assert measure_segment(line, tree, geoms) is None


def test_measure_segment_buildings_only_one_side_returns_none():
    """Only buildings on the right side — should not produce a width measurement."""
    line = LineString([(0, 0), (100, 0)])
    right_building = Polygon([(0, 10), (100, 10), (100, 15), (0, 15)])
    tree, geoms = _make_tree([right_building])
    # Left side has no buildings, so most samples won't have both sides
    result = measure_segment(line, tree, geoms)
    # Either None or filtered out by MIN_SAMPLES
    assert result is None


def test_measure_segment_iqr_is_small_for_uniform_road():
    """Uniform building alignment → IQR should be near zero."""
    line, tree, geoms = _road_with_buildings(7.5)
    result = measure_segment(line, tree, geoms)
    assert result is not None
    assert result["iqr_m"] < 2.0  # tight distribution for a uniform road


# ---------- verified width endpoint ----------

def test_verify_width_endpoint(client):
    r = client.post("/api/roads/chennai/segments/1-2-0/width/verify",
                    json={"width_m": 15.0, "note": "Field survey 2026-09-25"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["seg_id"] == "1-2-0"
    assert abs(body["width_m"] - 15.0) < 0.01
    assert body["width_source"] == "verified"


def test_verify_width_sticks_across_design(client):
    """After verifying a width, the design endpoint should use it."""
    client.post("/api/roads/chennai/segments/1-2-0/width/verify", json={"width_m": 20.0})
    r = client.post("/api/roads/chennai/segments/1-2-0/design", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["segment"]["road_width_source"] == "verified"
    assert abs(body["segment"]["road_width_m"] - 20.0) < 0.01


def test_verify_width_unknown_segment(client):
    assert client.post("/api/roads/chennai/segments/no-such/width/verify",
                       json={"width_m": 10.0}).status_code == 404


def test_verify_width_too_small(client):
    assert client.post("/api/roads/chennai/segments/1-2-0/width/verify",
                       json={"width_m": 1.0}).status_code == 422


def test_verify_width_too_large(client):
    assert client.post("/api/roads/chennai/segments/1-2-0/width/verify",
                       json={"width_m": 200.0}).status_code == 422
