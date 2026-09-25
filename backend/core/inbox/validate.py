"""Turn mapped cell values into typed values, row by row, with reasons for anything rejected."""
import re
from datetime import date, datetime, timedelta

import pandas as pd

EXCEL_EPOCH = date(1899, 12, 30)


class Invalid(ValueError):
    pass


def _blank(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and v.strip() in ("", "-", "NA", "N/A", "na", "n/a", "nil"))


def _number(v) -> float:
    if isinstance(v, bool):
        raise Invalid(f"'{v}' is not a number")
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    s = re.sub(r"\s*(m|mtr|mtrs|metres|meters|nos|no)\.?$", "", s, flags=re.I)  # "12 m", "450 nos"
    try:
        return float(s)
    except ValueError:
        raise Invalid(f"'{v}' is not a number") from None


def coerce(v, typ: str):
    """Returns the typed value, None for blank, or raises Invalid."""
    if _blank(v):
        return None
    if typ == "int":
        x = _number(v)
        if not float(x).is_integer():
            raise Invalid(f"'{v}' is not a whole number")
        return int(x)
    if typ == "float":
        return _number(v)
    if typ == "date":
        if isinstance(v, datetime):
            return v.date()
        if isinstance(v, date):
            return v
        if isinstance(v, (int, float)) and 20000 < float(v) < 80000:  # Excel serial day number
            return EXCEL_EPOCH + timedelta(days=int(v))
        s = str(v).strip()
        # ISO (2026-08-12) is year-month-day; everything else is read day-first, as written in India.
        iso = re.match(r"^\d{4}-\d{1,2}-\d{1,2}", s)
        d = pd.to_datetime(s, dayfirst=not iso, errors="coerce")
        if pd.isna(d):
            raise Invalid(f"'{v}' is not a date")
        return d.date()
    if typ == "string":
        return re.sub(r"\s+", " ", str(v)).strip()
    raise ValueError(f"Unknown field type '{typ}'")


def validate_rows(table: pd.DataFrame, mapping: dict[str, str], fields: dict, row_no_col: str) -> tuple[pd.DataFrame, list[dict]]:
    """Apply mapping {field: column} and types. Returns (clean rows incl. row_no, problems)."""
    out, problems = [], []
    for rec in table.to_dict("records"):
        row, errors = {"row_no": int(rec[row_no_col])}, []
        for f, col in mapping.items():
            spec = fields[f]
            try:
                val = coerce(rec.get(col), spec.get("type", "string"))
            except Invalid as e:
                errors.append(f"{spec.get('label', f)}: {e}")
                continue
            if val is not None and isinstance(val, (int, float)):
                if "min" in spec and val < spec["min"]:
                    errors.append(f"{spec.get('label', f)}: {val} is below the minimum {spec['min']}")
                if "max" in spec and val > spec["max"]:
                    errors.append(f"{spec.get('label', f)}: {val} is above the maximum {spec['max']}")
            row[f] = val
        for f, spec in fields.items():
            if spec.get("required") and row.get(f) is None and not any(f"{spec.get('label', f)}:" in e for e in errors):
                errors.append(f"{spec.get('label', f)} is required but empty")
        if errors:
            problems.append({"row_no": row["row_no"], "errors": errors})
        else:
            out.append(row)
    cols = ["row_no"] + list(mapping)
    return pd.DataFrame(out, columns=cols), problems
