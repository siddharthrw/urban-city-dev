import pytest

from modules.roads import widths

DEFAULTS = widths.load_defaults()


def test_every_default_is_labelled_and_sane():
    for cls, d in DEFAULTS["classes"].items():
        assert d["citation"], cls
        assert d["row_m"] > 2 * d["side_allowance_m"], cls


def test_class_default():
    w = widths.estimate("secondary", lanes=None, oneway=False, defaults=DEFAULTS)
    assert (w.width_m, w.source) == (DEFAULTS["classes"]["secondary"]["row_m"], "estimated")
    assert "UNCITED" in w.detail


def test_lanes_refine_two_way_roads():
    lane = DEFAULTS["lanes_refinement"]["lane_width_m"]
    side = DEFAULTS["classes"]["primary"]["side_allowance_m"]
    w = widths.estimate("primary", lanes=4, oneway=False, defaults=DEFAULTS)
    assert w.width_m == pytest.approx(4 * lane + 2 * side)
    assert "lanes=4" in w.detail and w.source == "estimated"


def test_lanes_ignored_on_one_way_and_divided_road_flagged():
    w = widths.estimate("primary", lanes=3, oneway=True, defaults=DEFAULTS)
    assert w.width_m == DEFAULTS["classes"]["primary"]["row_m"]
    assert "not used" in w.detail and "divided road" in w.detail


def test_unknown_class_falls_back_and_says_so():
    w = widths.estimate("busway", lanes=None, oneway=False, defaults=DEFAULTS)
    assert w.width_m == DEFAULTS["classes"]["unclassified"]["row_m"]
    assert "busway" in w.detail


def test_verified_beats_measured_beats_estimated():
    est = widths.Width(8, "estimated", "e")
    mea = widths.Width(9.3, "measured", "m")
    ver = widths.Width(10.1, "verified", "v")
    assert widths.resolve(est) is est
    assert widths.resolve(est, measured=mea) is mea
    assert widths.resolve(est, measured=mea, verified=ver) is ver
