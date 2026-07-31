"""Tests for the ATS text-layer verification check."""

from __future__ import annotations

from pathlib import Path

from backend.generation.application_pdf import generate_application_pdf
from backend.generation.ats_check import check_application_pdf, extract_pdf_text


def _make_pdf(tmp_path: Path) -> Path:
    cover_letter = (
        "Gabriel Strecker\n\n"
        "Sehr geehrte Damen und Herren,\n\n"
        "Ich habe Product Discovery für mehrere Teams eingeführt und "
        "Agentic-AI-Produktideen mit Pilotkunden validiert (Use-Case-Validierung).\n\n"
        "Mit freundlichen Grüßen\nGabriel Strecker\n"
    )
    cv = (
        "# Gabriel Strecker\n\n"
        "Marktheidenfeld, Bayern, Deutschland\n\n"
        "## Berufserfahrung\n"
        "- Product Discovery eingeführt.\n"
    )
    out = tmp_path / "application.pdf"
    return generate_application_pdf(cover_letter, cv, out)


def test_extract_pdf_text_returns_nonempty_text_and_page_count(tmp_path: Path):
    pdf_path = _make_pdf(tmp_path)
    text, page_count = extract_pdf_text(pdf_path)
    assert page_count == 2
    assert "Gabriel Strecker" in text


def test_check_application_pdf_passes_when_identity_and_signals_present(tmp_path: Path):
    pdf_path = _make_pdf(tmp_path)
    result = check_application_pdf(
        pdf_path,
        person_name="Gabriel Strecker",
        person_location="Marktheidenfeld, Bayern, Deutschland",
        matched_signals=["product_discovery", "ai_use_case_validation"],
    )
    assert result.passed
    assert result.warnings == []
    assert result.name_found
    assert result.location_found
    assert result.signals_missing == []
    assert set(result.signals_found) == {"product_discovery", "ai_use_case_validation"}


def test_check_application_pdf_flags_missing_name(tmp_path: Path):
    pdf_path = _make_pdf(tmp_path)
    result = check_application_pdf(pdf_path, person_name="Someone Else")
    assert not result.passed
    assert not result.name_found
    assert any("Someone Else" in w for w in result.warnings)


def test_check_application_pdf_flags_missing_location(tmp_path: Path):
    pdf_path = _make_pdf(tmp_path)
    result = check_application_pdf(
        pdf_path, person_name="Gabriel Strecker", person_location="Berlin, Deutschland"
    )
    assert not result.passed
    assert not result.location_found


def test_check_application_pdf_flags_missing_signal(tmp_path: Path):
    pdf_path = _make_pdf(tmp_path)
    result = check_application_pdf(
        pdf_path,
        person_name="Gabriel Strecker",
        matched_signals=["product_discovery", "govtech"],
    )
    assert not result.passed
    assert "govtech" in result.signals_missing
    assert "product_discovery" in result.signals_found


def test_check_application_pdf_no_location_or_signals_still_checks_name(tmp_path: Path):
    pdf_path = _make_pdf(tmp_path)
    result = check_application_pdf(pdf_path, person_name="Gabriel Strecker")
    assert result.passed
    assert result.location_found  # nothing to check -> defaults True
    assert result.signals_found == []
    assert result.signals_missing == []
