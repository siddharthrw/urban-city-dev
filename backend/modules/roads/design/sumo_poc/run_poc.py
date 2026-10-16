"""Proof-of-concept: does a real SUMO run produce a before/after travel-time comparison, end to
end, on this machine? NOT wired into the app — see docs/plan_sumo_simulation.md, "suggested first
slice". Run directly: `python -m modules.roads.design.sumo_poc.run_poc` from backend/.

Builds the smallest network that can produce a meaningful result (two nodes, one edge, standing in
for one road segment) rather than pulling real OSM data, generates a demand flow from the same
sample-PCU logic impact.py already uses (so the comparison is apples-to-apples with the BPR
estimate currently shown in the app), runs headless `sumo`, and reads back the simulated mean
travel time per vehicle from SUMO's own tripinfo output.

This intentionally does NOT touch impact.py or module.py — it's a standalone check that the SUMO
toolchain (eclipse-sumo + traci + sumolib, installed via pip) actually works here before any of
this is wired into the real API path.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

import sumo  # the eclipse-sumo package; exposes SUMO_HOME for the bundled binaries

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
from modules.roads.design.impact import sample_demand_pcu  # noqa: E402
import modules.roads.design as design_pkg  # noqa: E402
import yaml  # noqa: E402

DEFAULTS_PATH = os.path.join(os.path.dirname(design_pkg.__file__), "design_defaults.yaml")

SUMO_BIN = os.path.join(sumo.SUMO_HOME, "bin", "sumo.exe" if os.name == "nt" else "sumo")
NETCONVERT_BIN = os.path.join(sumo.SUMO_HOME, "bin", "netconvert.exe" if os.name == "nt" else "netconvert")

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


def _run_scenario(*, lanes_per_dir: int, length_m: float, free_flow_kmh: float, vehs_per_hour: float, workdir: str) -> dict:
    """Builds one network+demand pair and runs sumo headless. Returns mean travel time (minutes)
    and vehicle count actually completed, read from tripinfo.xml."""
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
        check=True, capture_output=True, text=True,
    )

    end_s = 3600
    with open(routes_path, "w") as f:
        f.write(ROUTES_XML.format(end_s=end_s, vehs_per_hour=vehs_per_hour))

    subprocess.run(
        [SUMO_BIN, "-n", net_path, "-r", routes_path, "--tripinfo-output", tripinfo_path,
         "--duration-log.disable", "true", "--no-step-log", "true", "--end", str(end_s + 300)],
        check=True, capture_output=True, text=True,
    )

    tree = ET.parse(tripinfo_path)
    trips = tree.getroot().findall("tripinfo")
    if not trips:
        return {"vehicles": 0, "mean_minutes": None}
    durations = [float(t.get("duration")) for t in trips]
    return {"vehicles": len(durations), "mean_minutes": round(sum(durations) / len(durations) / 60, 2)}


def main():
    cfg = yaml.safe_load(open(DEFAULTS_PATH))
    road_class = "secondary"
    length_m = 500.0
    free_flow_kmh = cfg["free_flow_kmh"].get(road_class, cfg["free_flow_kmh"]["unclassified"])
    pcu_per_hour, detail = sample_demand_pcu(road_class, cfg)
    print(f"Demand (reused from impact.py): {detail}\n")

    print(f"SUMO_HOME: {sumo.SUMO_HOME}\n")

    results = {}
    for label, lanes in [("Today (5 lanes/direction)", 5), ("Narrowed option (1 lane/direction)", 1)]:
        scen_dir = tempfile.mkdtemp(prefix="sumo_poc_")
        try:
            results[label] = _run_scenario(
                lanes_per_dir=lanes, length_m=length_m, free_flow_kmh=free_flow_kmh,
                vehs_per_hour=pcu_per_hour, workdir=scen_dir,
            )
        finally:
            shutil.rmtree(scen_dir, ignore_errors=True)

    print("Real SUMO simulation results (not the BPR estimate):")
    for label, r in results.items():
        print(f"  {label}: {r['vehicles']} vehicles completed, mean travel time {r['mean_minutes']} min")


if __name__ == "__main__":
    main()
