"""The real SUMO path (modules/roads/design/simulate.py) — skipped on a machine that hasn't
installed backend/requirements-sumo.txt, same as module.py's own fallback behaviour. This is the
one place that actually shells out to SUMO; keep it separate from test_design_api.py so that
suite stays fast and deterministic everywhere (see its _force_bpr_impact fixture)."""
import pytest

from modules.roads.design import simulate

pytestmark = pytest.mark.skipif(not simulate.available(), reason="SUMO not installed (backend/requirements-sumo.txt)")

CFG = {
    "free_flow_kmh": {"secondary": 35, "unclassified": 25},
    "classes": {"secondary": {"dir_default": 2}, "unclassified": {"dir_default": 1}},
    "sample_demand_load_factor": 0.75,
    "lane_capacity_pcu_per_hour": 1200,
}
CURRENT_ELEMENTS = [
    {"kind": "footpath", "width_cm": 150}, {"kind": "carriageway", "width_cm": 1500},
    {"kind": "footpath", "width_cm": 150},
]


def test_estimate_runs_a_real_simulation_and_returns_the_impact_shape():
    result = simulate.estimate(current_elements=CURRENT_ELEMENTS, option_lanes=2, oneway=False,
                               length_m=300, road_class="secondary", cfg=CFG)
    assert result["sample_data"] is True
    assert result["engine"] == "sumo"
    assert "SUMO" in result["note"]
    assert result["before"]["lanes"] >= 1
    assert result["after"]["lanes"] == 2
    assert result["before"]["minutes"] > 0 and result["after"]["minutes"] > 0
    assert isinstance(result["change_pct"], float)


def test_fewer_lanes_simulates_to_a_longer_or_equal_travel_time():
    # Same demand, much narrower option — a real congestion effect, not a monotonic formula, so
    # this only checks the direction holds at a wide enough gap to not be noise.
    result = simulate.estimate(current_elements=CURRENT_ELEMENTS, option_lanes=1, oneway=False,
                               length_m=300, road_class="secondary", cfg=CFG)
    assert result["after"]["minutes"] >= result["before"]["minutes"]
