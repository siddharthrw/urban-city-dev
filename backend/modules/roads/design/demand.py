"""People-and-movement data linked to a road -> the few numbers the engine uses.

Every number comes with a plain-words `detail` saying where it came from (which row, whether it is
SAMPLE data), because the design output must never present a made-up count as a real one.
Conversion factors are UNCITED settings in design_defaults.yaml.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Demand:
    peak_pcu: float | None = None        # peak-hour passenger-car units, both directions
    pcu_detail: str = ""
    peak_pedestrians: float | None = None  # pedestrians in the counted period, both sides
    ped_detail: str = ""
    bus_stops: int | None = None
    bus_detail: str = ""


def _tag(row: dict) -> str:
    return " (SAMPLE: made-up test data)" if row.get("is_sample") else ""


def _num(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def pcu_of_row(row: dict, factors: dict[str, float]) -> float | None:
    """PCU of one traffic-count row: from the per-type counts if any are present (so the
    conversion factors apply), else from its total_vehicles counted as cars."""
    parts = [(k, _num(row.get(k))) for k in factors]
    parts = [(k, v) for k, v in parts if v is not None]
    if parts:
        return sum(factors[k] * v for k, v in parts)
    total = _num(row.get("total_vehicles"))
    return total if total is not None else None


def build_demand(traffic_rows: list[dict], footfall_rows: list[dict], bus_rows: list[dict],
                 pcu_factors: dict[str, float]) -> Demand:
    peak, peak_row = None, None
    for r in traffic_rows:
        p = pcu_of_row(r, pcu_factors)
        if p is not None and (peak is None or p > peak):
            peak, peak_row = p, r
    pcu_detail = ""
    if peak_row is not None:
        n = len(traffic_rows)
        pcu_detail = (f"Highest of {n} traffic count{'s' if n != 1 else ''} linked to this road: row "
                      f"{peak_row.get('row_no')}{_tag(peak_row)}, about {peak:,.0f} PCU"
                      f"{' at ' + str(peak_row['time_period']) if peak_row.get('time_period') else ''}.")

    ped, ped_row = None, None
    for r in footfall_rows:
        v = _num(r.get("pedestrians"))
        if v is not None and (ped is None or v > ped):
            ped, ped_row = v, r
    ped_detail = ""
    if ped_row is not None:
        ped_detail = (f"Highest pedestrian count linked to this road: row {ped_row.get('row_no')}"
                      f"{_tag(ped_row)}, {ped:,.0f} people"
                      f"{' in ' + str(ped_row['time_period']) if ped_row.get('time_period') else ''}"
                      " (treated as a peak-hour count).")

    stops = len(bus_rows) if bus_rows else None
    bus_detail = ""
    if bus_rows:
        tagged = " (SAMPLE: made-up test data)" if any(r.get("is_sample") for r in bus_rows) else ""
        bus_detail = f"{len(bus_rows)} bus stop(s) linked to this road{tagged}."
    return Demand(peak, pcu_detail, ped, ped_detail, stops, bus_detail)
