"""Tests for the combined cover-letter + CV application PDF renderer."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from backend.generation.application_pdf import generate_application_pdf


def test_generate_application_pdf_puts_cover_letter_on_page_one(tmp_path: Path):
    cover_letter = (
        "Gabriel Strecker\n\n"
        "Sehr geehrte Damen und Herren,\n\n"
        "hiermit bewerbe ich mich als Senior Product Manager.\n\n"
        "Mit freundlichen Grüßen\nGabriel Strecker\n"
    )
    cv = (
        "# Gabriel Strecker\n\n"
        "## Profil\n"
        "Ausrichtung: Senior Product Manager.\n\n"
        "## Berufserfahrung\n"
        "- Beispiel-Bullet.\n"
    )
    out = tmp_path / "application.pdf"
    path = generate_application_pdf(cover_letter, cv, out)

    assert path == out
    assert path.is_file()
    assert path.stat().st_size > 0

    reader = PdfReader(str(path))
    assert len(reader.pages) >= 2

    page_one_text = reader.pages[0].extract_text() or ""
    page_two_text = reader.pages[1].extract_text() or ""

    assert "Sehr geehrte Damen und Herren" in page_one_text
    assert "Profil" not in page_one_text

    assert "Ausrichtung: Senior Product Manager" in page_two_text
    assert "Sehr geehrte Damen und Herren" not in page_two_text


def test_generate_application_pdf_strips_markdown_from_cover_letter(tmp_path: Path):
    cover_letter = "**Gabriel Strecker**\n\n> ein Zitat\n\nAbsatz mit `code`.\n"
    cv = "# CV\n\nInhalt.\n"
    out = tmp_path / "application.pdf"
    generate_application_pdf(cover_letter, cv, out)

    text = PdfReader(str(out)).pages[0].extract_text() or ""
    assert "**" not in text
    assert "`" not in text
