from datetime import date, datetime

import pandas as pd
import pytest

from core.inbox.validate import Invalid, coerce, validate_rows


@pytest.mark.parametrize("v, typ, expected", [
    ("1,250", "int", 1250),
    (1250.0, "int", 1250),
    ("450 nos", "int", 450),
    ("24.5 m", "float", 24.5),
    ("18 mtr", "float", 18.0),
    ("12/08/2026", "date", date(2026, 8, 12)),       # Indian day-first
    ("2026-08-12", "date", date(2026, 8, 12)),
    (datetime(2026, 8, 12, 9, 0), "date", date(2026, 8, 12)),
    (46246, "date", date(2026, 8, 12)),              # Excel serial number
    ("  North   Usman Rd ", "string", "North Usman Rd"),
    ("", "int", None), ("-", "float", None), ("NA", "date", None), (None, "string", None), (float("nan"), "int", None),
])
def test_coerce(v, typ, expected):
    assert coerce(v, typ) == expected


@pytest.mark.parametrize("v, typ", [("abc", "int"), ("12.5", "int"), ("twelve", "float"), ("not a date", "date"), (True, "int")])
def test_coerce_rejects(v, typ):
    with pytest.raises(Invalid):
        coerce(v, typ)


def test_unknown_type_is_a_programming_error():
    with pytest.raises(ValueError):
        coerce("x", "colour")


FIELDS = {
    "cars": {"type": "int", "label": "Cars", "min": 0},
    "width_m": {"type": "float", "label": "Width", "required": True, "min": 2, "max": 150},
    "road_name": {"type": "string", "label": "Road name"},
}


def test_validate_rows_reports_every_problem_with_row_numbers():
    t = pd.DataFrame({
        "_row_no": [4, 5, 6, 7],
        "Cars": ["10", "abc", "-5", "3"],
        "W": ["12 m", "8", "", "900"],
        "Road": ["A", "B", "C", "D"],
    })
    clean, problems = validate_rows(t, {"cars": "Cars", "width_m": "W", "road_name": "Road"}, FIELDS, "_row_no")
    assert clean.to_dict("records") == [{"row_no": 4, "cars": 10, "width_m": 12.0, "road_name": "A"}]
    by_row = {p["row_no"]: p["errors"] for p in problems}
    assert by_row[5] == ["Cars: 'abc' is not a number"]
    assert by_row[6] == ["Cars: -5 is below the minimum 0", "Width is required but empty"]
    assert by_row[7] == ["Width: 900.0 is above the maximum 150"]


def test_required_field_not_mapped_counts_as_empty():
    t = pd.DataFrame({"_row_no": [2], "Road": ["A"]})
    clean, problems = validate_rows(t, {"road_name": "Road"}, FIELDS, "_row_no")
    assert clean.empty and problems[0]["errors"] == ["Width is required but empty"]
