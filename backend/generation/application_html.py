"""Combine a styled cover letter + styled CV into one PDF via Playwright.

Same "combined application PDF" contract as application_pdf.py (cover
letter on page 1, CV from page 2), but rendered through cv_html.py's
CSS/typography instead of fpdf2's plain single-column text.

Cover letter parsing assumes the fixed convention every anschreiben.md in
this repo already follows (see cv-tailor style rules): sender block,
recipient block, date line, subject line, salutation, one or more body
paragraphs, closing — each separated by a blank line.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

from backend.generation.cv_html import cv_content_html, cv_css
from backend.models import CvMaster, CvRules, SelectionPlan

_LETTER_CSS = """
.letter-sender { font-size: 9.3pt; color: #5b6472; margin-bottom: 9mm; }
.letter-sender .name { font-weight: 700; color: #1a1a1a; font-size: 10pt; }
.letter-recipient { font-size: 10pt; margin-bottom: 7mm; }
.letter-date { font-size: 9.3pt; color: #5b6472; margin-bottom: 7mm; }
.letter-subject {
  font-size: 11.3pt; font-weight: 700; color: #1f3a5f; margin-bottom: 5mm;
}
.letter-salutation { margin-bottom: 4mm; }
.letter-paragraph { margin-bottom: 4mm; }
.letter-paragraph:last-of-type { margin-bottom: 7mm; }
.letter-closing .signoff { margin-bottom: 8mm; }
.cv-page-break { page-break-before: always; break-before: page; }
"""


class CoverLetterFormatError(ValueError):
    """Raised when anschreiben.md doesn't match the expected block layout."""


def parse_cover_letter(text: str) -> dict:
    """Split a DIN-5008-style letter into its fixed blocks.

    Blocks are separated by blank lines, in this order: sender, recipient,
    date, subject, salutation, one-or-more paragraphs, closing.
    """
    blocks = [b.strip() for b in text.strip().split("\n\n") if b.strip()]
    if len(blocks) < 7:
        raise CoverLetterFormatError(
            f"Expected at least 7 blank-line-separated blocks (sender, recipient, "
            f"date, subject, salutation, >=1 paragraph, closing), got {len(blocks)}."
        )
    return {
        "sender_lines": blocks[0].splitlines(),
        "recipient_lines": blocks[1].splitlines(),
        "date_line": blocks[2],
        "subject_line": blocks[3],
        "salutation": blocks[4],
        "paragraphs": blocks[5:-1],
        "closing_lines": blocks[-1].splitlines(),
    }


def _cover_letter_content_html(cover_letter_text: str) -> str:
    parsed = parse_cover_letter(cover_letter_text)

    sender_lines = parsed["sender_lines"]
    sender_html = "".join(
        f'<div class="name">{escape(sender_lines[0])}</div>'
        if i == 0
        else f"<div>{escape(line)}</div>"
        for i, line in enumerate(sender_lines)
    )
    recipient_html = "".join(f"<div>{escape(line)}</div>" for line in parsed["recipient_lines"])
    paragraphs_html = "".join(
        f'<p class="letter-paragraph">{escape(p)}</p>' for p in parsed["paragraphs"]
    )
    closing_html = "".join(
        f'<div class="signoff">{escape(line)}</div>' if i == 0 else f"<div>{escape(line)}</div>"
        for i, line in enumerate(parsed["closing_lines"])
    )

    return (
        f'<div class="letter-sender">{sender_html}</div>'
        f'<div class="letter-recipient">{recipient_html}</div>'
        f'<div class="letter-date">{escape(parsed["date_line"])}</div>'
        f'<div class="letter-subject">{escape(parsed["subject_line"])}</div>'
        f'<div class="letter-salutation">{escape(parsed["salutation"])}</div>'
        f"{paragraphs_html}"
        f'<div class="letter-closing">{closing_html}</div>'
    )


def generate_application_html(
    cover_letter_text: str,
    selection_plan: SelectionPlan,
    cv_master: CvMaster,
    cv_rules: CvRules,
) -> str:
    """Full HTML document: styled cover letter (page 1) + styled CV (from page 2)."""
    letter_html = _cover_letter_content_html(cover_letter_text)
    cv_html = cv_content_html(selection_plan, cv_master, cv_rules)
    css = cv_css() + _LETTER_CSS
    person_name = escape(cv_master.person.name)
    return (
        "<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\">"
        f"<title>{person_name}</title><style>{css}</style></head>"
        f"<body>{letter_html}"
        f'<div class="cv-page-break">{cv_html}</div>'
        "</body></html>"
    )


def generate_application_pdf_html(
    cover_letter_text: str,
    selection_plan: SelectionPlan,
    cv_master: CvMaster,
    cv_rules: CvRules,
    out_path: Path | str,
) -> Path:
    """Render the combined styled application and print it to PDF."""
    from playwright.sync_api import sync_playwright

    html = generate_application_html(cover_letter_text, selection_plan, cv_master, cv_rules)
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            page.pdf(
                path=str(path),
                format="A4",
                print_background=True,
                margin={"top": "0mm", "bottom": "0mm", "left": "0mm", "right": "0mm"},
            )
        finally:
            browser.close()
    return path
