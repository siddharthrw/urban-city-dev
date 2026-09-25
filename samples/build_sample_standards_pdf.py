r"""Builds samples/SAMPLE_standards_excerpt.pdf: a small, entirely made-up "standards document"
used to test and demo the document-ingestion -> extraction -> review pipeline (core/rules/).

Run once with: ..\.venv\Scripts\python.exe samples\build_sample_standards_pdf.py
The output is committed, so this script does not need to run again unless the sample text changes.
"""
from pathlib import Path

from fpdf import FPDF

PAGES = [
    ("1", "Introduction",
     "SAMPLE STANDARD - MADE UP FOR TESTING, NOT A REAL DOCUMENT.\n\n"
     "This is a fabricated excerpt used only to test the document ingestion and rule "
     "extraction pipeline. It is formatted like a road design standard but states no real "
     "requirements and must never be treated as one."),
    ("6", "5. Footpaths",
     "5.1 The minimum width of a footpath shall be 1.8 m in residential areas.\n\n"
     "5.2 In commercial and market streets, the minimum footpath width shall be 2.5 m to "
     "allow for higher pedestrian volumes.\n\n"
     "5.3 Footpaths shall be free of obstructions such as poles and signage within the "
     "clear walking zone."),
    ("11", "7. Cycle Tracks",
     "7.1 A one-way cycle track shall not be less than 2.0 m wide.\n\n"
     "7.2 A two-way cycle track shall not be less than 2.5 m wide, exclusive of any "
     "separating buffer from motor traffic."),
    ("14", "9. Bus Bays",
     "9.1 A bus bay shall be a minimum of 3.0 m wide in addition to the adjoining traffic "
     "lane, with an entry taper of not less than 15 m."),
]


def build(out: Path) -> None:
    pdf = FPDF()
    pdf.set_auto_page_break(True, margin=15)
    for page_no, heading, body in PAGES:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.multi_cell(0, 8, f"p.{page_no}  {heading}")
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 6, body)
    pdf.output(str(out))


if __name__ == "__main__":
    build(Path(__file__).with_name("SAMPLE_standards_excerpt.pdf"))
    print("wrote", Path(__file__).with_name("SAMPLE_standards_excerpt.pdf"))
