"""Simple ATS-safe single-column PDF export from plain or markdown CV text.

Boring layout only: no columns, tables, graphics, or decorative styling.
Uses fpdf2 + bundled DejaVuSans for German Unicode on macOS/CI.
"""

from __future__ import annotations

import re
from pathlib import Path

from fpdf import FPDF

_FONT_PATH = Path(__file__).resolve().parent / "fonts" / "DejaVuSans.ttf"

# Strip markdown heading markers / emphasis for a plain ATS body.
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_MD_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_MD_BLOCKQUOTE_RE = re.compile(r"^>\s?", re.MULTILINE)
_MD_CODE_RE = re.compile(r"`([^`]+)`")


def _to_ats_plain(plain_or_md_text: str) -> str:
    """Normalize markdown-ish CV text to single-column plain lines."""
    text = plain_or_md_text.replace("\r\n", "\n").replace("\r", "\n")
    text = _MD_HEADING_RE.sub("", text)
    text = _MD_BLOCKQUOTE_RE.sub("", text)
    text = _MD_BOLD_RE.sub(r"\1", text)
    text = _MD_ITALIC_RE.sub(r"\1", text)
    text = _MD_CODE_RE.sub(r"\1", text)
    # Collapse 3+ blank lines; keep paragraph breaks.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def generate_cv_variant_pdf(plain_or_md_text: str, out_path: Path | str) -> Path:
    """Write a boring single-column ATS PDF from plain or markdown CV text.

    Returns the written path. Does not invent content; layout is Helvetica-like
    body text only (DejaVuSans for Unicode).
    """
    body = _to_ats_plain(plain_or_md_text)
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
    pdf.add_page()
    pdf.add_font("DejaVu", fname=str(_FONT_PATH))
    pdf.set_font("DejaVu", size=10)
    # multi_cell: full usable width, modest line height, left-aligned.
    pdf.multi_cell(w=0, h=5, text=body, align="L")
    pdf.output(str(path))
    return path
