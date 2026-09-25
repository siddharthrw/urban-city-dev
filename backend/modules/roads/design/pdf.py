"""One-page PDF export for a road design result.

Uses fpdf2. The cross-section is drawn as coloured rectangles proportional to the right-of-way.
No LLM here; explanations from explain.py are passed in by the caller when available.
"""
from io import BytesIO

from fpdf import FPDF, XPos, YPos

_ELEMENT_COLORS: dict[str, tuple[int, int, int]] = {
    "footpath":    (170, 220, 170),
    "tree_strip":  (80,  160, 80),
    "cycle_track": (120, 180, 240),
    "bus_bay":     (255, 200, 100),
    "lane":        (190, 190, 210),
    "median":      (140, 140, 160),
}
_DEFAULT_COLOR: tuple[int, int, int] = (200, 200, 200)

_MARGIN = 15.0
_USABLE_W = 210.0 - 2 * _MARGIN  # A4 portrait, 210 mm wide


def _cross_section(pdf: FPDF, elements: list[dict], row_cm: int,
                   x0: float, y0: float, w: float, h: float) -> None:
    x = x0
    for el in elements:
        el_w = (el["width_cm"] / row_cm) * w
        r, g, b = _ELEMENT_COLORS.get(el["kind"], _DEFAULT_COLOR)
        pdf.set_fill_color(r, g, b)
        pdf.rect(x, y0, el_w, h, style="F")
        if el_w >= 5:
            pdf.set_font("Helvetica", "", 6)
            pdf.set_text_color(40, 40, 40)
            pdf.set_xy(x, y0 + h / 2 - 2)
            pdf.cell(el_w, 4, f"{el['width_m']:g}m", align="C")
        x += el_w
    pdf.set_text_color(0, 0, 0)


def _legend(pdf: FPDF, elements: list[dict]) -> None:
    seen: list[str] = []
    for el in elements:
        if el["kind"] not in seen:
            seen.append(el["kind"])
    x = _MARGIN
    y = pdf.get_y() + 1
    for kind in seen:
        r, g, b = _ELEMENT_COLORS.get(kind, _DEFAULT_COLOR)
        pdf.set_fill_color(r, g, b)
        pdf.rect(x, y, 4, 3, style="F")
        pdf.set_font("Helvetica", "", 6)
        pdf.set_text_color(60, 60, 60)
        pdf.set_xy(x + 5, y - 0.5)
        pdf.cell(24, 4, kind.replace("_", " ").title())
        x += 30
    pdf.set_text_color(0, 0, 0)
    pdf.ln(6)


def _option_section(pdf: FPDF, opt: dict, result: dict, explanation: str) -> None:
    m = opt["metrics"]

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, opt["name"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(80, 80, 80)
    pdf.multi_cell(_USABLE_W, 4.5, opt["summary"])
    pdf.set_text_color(0, 0, 0)

    cs_y = pdf.get_y() + 1
    _cross_section(pdf, opt["elements"], result["row_cm"], _MARGIN, cs_y, _USABLE_W, 14)
    pdf.set_y(cs_y + 14 + 1)
    _legend(pdf, opt["elements"])

    feat = [label for label, flag in [
        ("cycle track", m["has_cycle_track"]), ("trees", m["has_trees"]),
        ("bus bays", m["has_bus_bay"]), ("median", m["has_median"]),
    ] if flag]
    metrics = (f"Lanes: {m['lanes']}  Lane: {m['lane_width_m']:.1f} m  "
               f"Footpath: {m['footpath_m']:.1f} m each side"
               + (("  " + "  ".join(feat)) if feat else ""))
    pdf.set_font("Helvetica", "", 8)
    pdf.multi_cell(_USABLE_W, 4.5, metrics)

    if opt["omitted"] or opt["notes"]:
        pdf.set_font("Helvetica", "I", 7.5)
        pdf.set_text_color(120, 90, 0)
        for o in opt["omitted"]:
            pdf.multi_cell(_USABLE_W, 4, f"  - {o['reason']}")
        for n in opt["notes"]:
            pdf.multi_cell(_USABLE_W, 4, f"  * {n}")
        pdf.set_text_color(0, 0, 0)

    if explanation:
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(30, 60, 100)
        pdf.multi_cell(_USABLE_W, 4.5, explanation)
        pdf.set_text_color(0, 0, 0)

    rules = result.get("rules", {})
    if opt["rule_ids"]:
        pdf.set_font("Helvetica", "I", 7)
        pdf.set_text_color(130, 130, 130)
        for rid in opt["rule_ids"]:
            if rid in rules:
                auth = rules[rid]["authority"].upper()
                pdf.multi_cell(_USABLE_W, 3.5,
                               f"[{auth}] {rid}: {rules[rid]['statement']}")
        pdf.set_text_color(0, 0, 0)

    pdf.ln(4)


class _DesignPDF(FPDF):
    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(150, 150, 150)
        self.cell(0, 5,
                  "City Planning OS  |  Not a statutory document  |  All dimensions subject to survey",
                  align="C")
        self.set_text_color(0, 0, 0)


def build_pdf(result: dict, explanations: dict | None = None) -> bytes:
    """Build and return a PDF (bytes) for a design result.

    `explanations` is the dict returned by ``explain()``: keys ``explanations`` (per-option)
    and ``comparison`` (overall text). Pass ``None`` to produce a PDF without LLM text.
    """
    exps: dict[str, str] = (explanations or {}).get("explanations", {})
    comparison: str = (explanations or {}).get("comparison", "")

    pdf = _DesignPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_left_margin(_MARGIN)
    pdf.set_right_margin(_MARGIN)

    seg = result.get("segment", {})
    road_name = seg.get("name") or "Unnamed road"

    # Header
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, f"Road Design: {road_name}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(80, 80, 80)
    ctx = result.get("context", [])
    ctx_str = ("  |  Context: " + ", ".join(c.replace("_", " ") for c in ctx)) if ctx else ""
    pdf.cell(0, 5,
             f"{result['row_m']:g} m right-of-way ({result['width_source']})  |  "
             f"{result['road_class'].replace('_', ' ')}  |  "
             f"{'one-way' if result['oneway'] else 'two-way'}{ctx_str}",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    # Warnings box
    if result.get("warnings"):
        pdf.set_fill_color(255, 248, 225)
        pdf.set_draw_color(210, 170, 50)
        pdf.set_font("Helvetica", "I", 7.5)
        pdf.set_text_color(120, 80, 0)
        warn = "WARNINGS: " + "  |  ".join(result["warnings"])
        pdf.multi_cell(_USABLE_W, 4.5, warn, border=1, fill=True)
        pdf.set_text_color(0, 0, 0)
        pdf.set_draw_color(0, 0, 0)
        pdf.set_fill_color(255, 255, 255)
        pdf.ln(3)

    # LLM comparison / recommendation
    if comparison:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, "Recommendation", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(_USABLE_W, 4.5, comparison)
        pdf.ln(2)

    # Options
    if result.get("options"):
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 6, "Design Options", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_draw_color(200, 200, 200)
        pdf.line(_MARGIN, pdf.get_y(), 210 - _MARGIN, pdf.get_y())
        pdf.set_draw_color(0, 0, 0)
        pdf.ln(2)
        for opt in result["options"]:
            _option_section(pdf, opt, result, exps.get(opt["option_id"], ""))
    else:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 8, "No option fits at this width.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Dropped options
    if result.get("dropped"):
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, "Not possible at this width", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 8)
        for d in result["dropped"]:
            pdf.multi_cell(_USABLE_W, 4.5, f"* {d['name']}: {d['reason']}")

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()
