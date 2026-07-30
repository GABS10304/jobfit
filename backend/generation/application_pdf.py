"""Combine cover letter + CV into one application PDF (Anschreiben + CV).

Same boring single-column ATS style as cv_pdf.py (same font/margins) — just a
page break between the two documents. No new layout engine: reuses
_to_ats_plain for both bodies.
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

from backend.generation.cv_pdf import _FONT_PATH, _to_ats_plain


def generate_application_pdf(
    cover_letter_text: str,
    cv_text: str,
    out_path: Path | str,
) -> Path:
    """Write cover letter (page 1) + page break + CV (from page 2) as one PDF."""
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not _FONT_PATH.is_file():
        raise FileNotFoundError(
            f"Bundled ATS PDF font missing: {_FONT_PATH}. "
            "Expected DejaVuSans.ttf next to cv_pdf.py."
        )

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(left=18, top=18, right=18)
    pdf.add_font("DejaVu", fname=str(_FONT_PATH))
    pdf.set_font("DejaVu", size=10)

    pdf.add_page()
    pdf.multi_cell(w=0, h=5, text=_to_ats_plain(cover_letter_text), align="L")

    pdf.add_page()
    pdf.multi_cell(w=0, h=5, text=_to_ats_plain(cv_text), align="L")

    pdf.output(str(path))
    return path
