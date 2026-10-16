"""Real SUMO-based before/after travel-time estimate — see docs/plan_sumo_simulation.md.

Same inputs/shape as `impact.estimate()`: given the current cross-section, an option's lane
count, and the segment's own length, builds a minimal straight-line network sized to that length
(not the full curved alignment — see "next slice" in the plan doc), runs headless SUMO once for
today's inferred lane count and once for the option's, and reads the simulated mean travel time
per vehicle back from SUMO's own tripinfo output — a real emergent result, not a formula.

Demand is still `sample_demand_pcu()` from impact.py — there is no real traffic count behind this
either way, so `sample_data` stays True and the note says so; what changed is that the *travel
time* is now actually simulated instead of computed from the BPR curve.

eclipse-sumo/traci/sumolib (pip-installable, bundle the real SUMO binaries) are NOT in
backend/requirements.txt — a ~270MB download that would make every normal app run/CI need it.
`available()` reports whether this environment has them; module.py falls back to impact.py's BPR
estimate when it doesn't, so other machines/branches keep working unmodified.
"""
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from functools import lru_cache

from modules.roads.design.impact import _free_flow_kmh, _infer_current_lanes, sample_demand_pcu

try:
    import sumo as _sumo_pkg
    SUMO_HOME: str | None = _sumo_pkg.SUMO_HOME
except ImportError:
    SUMO_HOME = None

SUMO_BIN = os.path.join(SUMO_HOME, "bin", "sumo.exe" if os.name == "nt" else "sumo") if SUMO_HOME else None
NETCONVERT_BIN = os.path.join(SUMO_HOME, "bin", "netconvert.exe" if os.name == "nt" else "netconvert") if SUMO_HOME else None

SIM_WINDOW_S = 900  # 15 simulated minutes of demand — enough vehicles for a stable mean without
                     # making an API request take minutes; two scenarios run per design option.
RUN_TIMEOUT_S = 30  # guards against a hung subprocess turning into a hung API request

NODES_XML = """<nodes>
  <node id="A" x="0" y="0"/>
  <node id="B" x="{length_m}" y="0"/>
</nodes>
"""
EDGES_XML = """<edges>
  <edge id="seg" from="A" to="B" numLanes="{lanes_per_dir}" speed="{speed_mps:.2f}"/>
</edges>
"""
ROUTES_XML = """<routes>
  <vType id="car" length="4.5" maxSpeed="40" accel="2.6" decel="4.5"/>
  <flow id="f" type="car" from="seg" to="seg" begin="0" end="{end_s}" vehsPerHour="{vehs_per_hour:.0f}"/>
</routes>
"""


def available() -> bool:
    return bool(SUMO_HOME and SUMO_BIN and os.path.exists(SUMO_BIN))


def _dir_lanes(lanes: int, oneway: bool) -> int:
    return max(1, round(lanes if oneway else lanes / 2))


@lru_cache(maxsize=64)
def _run_scenario(lanes_per_dir: int, length_m: float, free_flow_kmh: float, vehs_per_hour: float) -> tuple[float, int]:
    """Runs one netconvert+sumo pair and returns (mean_minutes, vehicles_completed). Memoized on
    its scalar inputs: a design request asks for the same "today" scenario once per option on
    that segment, and repeat requests for the same segment/option hit this too, for free."""
    with tempfile.TemporaryDirectory(prefix="sumo_sim_") as workdir:
        nodes_path = os.path.join(workdir, "nodes.nod.xml")
        edges_path = os.path.join(workdir, "edges.edg.xml")
        net_path = os.path.join(workdir, "net.net.xml")
        routes_path = os.path.join(workdir, "routes.rou.xml")
        tripinfo_path = os.path.join(workdir, "tripinfo.xml")

        with open(nodes_path, "w") as f:
            f.write(NODES_XML.format(length_m=length_m))
        with open(edges_path, "w") as f:
            f.write(EDGES_XML.format(lanes_per_dir=lanes_per_dir, speed_mps=free_flow_kmh / 3.6))
        subprocess.run(
            [NETCONVERT_BIN, "--node-files", nodes_path, "--edge-files", edges_path, "-o", net_path],
            check=True, capture_output=True, text=True, timeout=RUN_TIMEOUT_S,
        )

        with open(routes_path, "w") as f:
            f.write(ROUTES_XML.format(end_s=SIM_WINDOW_S, vehs_per_hour=vehs_per_hour))
        subprocess.run(
            [SUMO_BIN, "-n", net_path, "-r", routes_path, "--tripinfo-output", tripinfo_path,
             "--duration-log.disable", "true", "--no-step-log", "true", "--end", str(SIM_WINDOW_S + 300)],
            check=True, capture_output=True, text=True, timeout=RUN_TIMEOUT_S,
        )

        trips = ET.parse(tripinfo_path).getroot().findall("tripinfo")
        if not trips:
            # Demand too low / lanes too narrow for any vehicle to clear the edge inside the
            # window — fall back to the free-flow time rather than returning nothing.
            return round((length_m / 1000) / free_flow_kmh * 60, 2), 0
        durations = [float(t.get("duration")) for t in trips]
        return round(sum(durations) / len(durations) / 60, 2), len(durations)


def estimate(*, current_elements: list[dict], option_lanes: int, oneway: bool, length_m: float,
            road_class: str, cfg: dict) -> dict:
    """Same shape as impact.estimate(). Raises RuntimeError if SUMO isn't available in this
    environment, or OSError/subprocess errors if a run fails — module.py catches these and falls
    back to the BPR estimate."""
    if not available():
        raise RuntimeError("SUMO is not installed in this environment")

    length_m = length_m if length_m and length_m > 0 else 100.0
    before_lanes = _infer_current_lanes(current_elements)
    pcu, pcu_detail = sample_demand_pcu(road_class, cfg)
    free_flow_kmh = _free_flow_kmh(road_class, cfg)
    capacity_per_lane = cfg["lane_capacity_pcu_per_hour"]

    before_dir_lanes = _dir_lanes(before_lanes, oneway)
    after_dir_lanes = _dir_lanes(option_lanes, oneway)
    before_minutes, before_vehicles = _run_scenario(before_dir_lanes, length_m, free_flow_kmh, pcu)
    after_minutes, after_vehicles = _run_scenario(after_dir_lanes, length_m, free_flow_kmh, pcu)

    before = {"lanes": before_lanes, "vc_ratio": round(pcu / (before_dir_lanes * capacity_per_lane), 2),
              "free_flow_kmh": free_flow_kmh, "minutes": before_minutes}
    after = {"lanes": option_lanes, "vc_ratio": round(pcu / (after_dir_lanes * capacity_per_lane), 2),
             "free_flow_kmh": free_flow_kmh, "minutes": after_minutes}
    change_pct = ((after["minutes"] - before["minutes"]) / before["minutes"] * 100) if before["minutes"] else 0.0

    return {
        "sample_data": True,  # the DEMAND is still sample (no real traffic count) — see module docstring
        "engine": "sumo",
        "note": ("Real SUMO microsimulation (not a formula) using a SAMPLE traffic volume — there's "
                 "still no real traffic count behind the demand, but the travel time below is an "
                 f"actual simulated result ({before_vehicles} / {after_vehicles} vehicles completed "
                 "in the simulated window)."),
        "sample_pcu": round(pcu), "sample_pcu_detail": pcu_detail,
        "length_m": length_m, "before": before, "after": after, "change_pct": round(change_pct, 1),
    }
