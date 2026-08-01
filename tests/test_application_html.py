"""Tests for the styled HTML/Playwright application renderer (cover letter + CV)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend import data_loader, fit_engine
from backend.generation.application_html import (
    CoverLetterFormatError,
    generate_application_html,
    generate_application_pdf_html,
    parse_cover_letter,
)
from backend.generation.selection_plan import selection_plan

JD_TEXT = (
    "AI Product Manager (m/w/d)\n\nBerlin, Remote\n\n"
    "Product Discovery, AI-Use-Case-Validierung, Python, LLM-Integrationen."
)

COVER_LETTER = """Gabriel Strecker
Marktheidenfeld, Bayern

TestCo
Recruiting
Berlin

Marktheidenfeld, 1. August 2026

Bewerbung als AI Product Manager (m/w/d)

Sehr geehrte Damen und Herren,

Erster Absatz mit dem Aufhänger.

Zweiter Absatz mit Belegen.

Mit freundlichen Grüßen
Gabriel Strecker
"""


@pytest.fixture(scope="module")
def sample_plan():
    cv_master = data_loader.load_cv_master()
    role_fit_profile = data_loader.load_role_fit_profile()
    constraints = data_loader.load_constraints()
    cv_rules = data_loader.load_cv_rules()
    fit = fit_engine.run_fit_check(
        job_description=JD_TEXT, profile=role_fit_profile, constraints=constraints
    )
    plan = selection_plan(cv_master, role_fit_profile, fit, JD_TEXT, cv_rules)
    return plan, cv_master, cv_rules


def test_parse_cover_letter_splits_fixed_blocks():
    parsed = parse_cover_letter(COVER_LETTER)
    assert parsed["sender_lines"] == ["Gabriel Strecker", "Marktheidenfeld, Bayern"]
    assert parsed["recipient_lines"] == ["TestCo", "Recruiting", "Berlin"]
    assert parsed["date_line"] == "Marktheidenfeld, 1. August 2026"
    assert parsed["subject_line"] == "Bewerbung als AI Product Manager (m/w/d)"
    assert parsed["salutation"] == "Sehr geehrte Damen und Herren,"
    assert parsed["paragraphs"] == [
        "Erster Absatz mit dem Aufhänger.",
        "Zweiter Absatz mit Belegen.",
    ]
    assert parsed["closing_lines"] == ["Mit freundlichen Grüßen", "Gabriel Strecker"]


def test_parse_cover_letter_rejects_too_few_blocks():
    with pytest.raises(CoverLetterFormatError):
        parse_cover_letter("Just one block.")


def test_generate_application_html_has_no_unformatted_css_braces(sample_plan):
    """Regression: _LETTER_CSS must not leak literal {{ }} into the output —
    that silently breaks the whole letter stylesheet (incl. the page break)."""
    plan, cv_master, cv_rules = sample_plan
    html = generate_application_html(COVER_LETTER, plan, cv_master, cv_rules)
    assert "{{" not in html
    assert "}}" not in html
    assert "page-break-before: always" in html


def test_generate_application_html_contains_letter_and_cv_content(sample_plan):
    plan, cv_master, cv_rules = sample_plan
    html = generate_application_html(COVER_LETTER, plan, cv_master, cv_rules)
    assert "Erster Absatz mit dem Aufhänger." in html
    assert cv_master.person.name in html
    assert "cv-page-break" in html


def test_generate_application_pdf_html_separates_letter_and_cv_pages(
    tmp_path: Path, sample_plan
):
    pytest.importorskip("playwright.sync_api")
    plan, cv_master, cv_rules = sample_plan

    try:
        out = generate_application_pdf_html(
            COVER_LETTER, plan, cv_master, cv_rules, tmp_path / "application.pdf"
        )
    except Exception as exc:  # pragma: no cover - environment without browser binaries
        pytest.skip(f"Playwright Chromium not available: {exc}")

    from pypdf import PdfReader

    reader = PdfReader(str(out))
    assert len(reader.pages) >= 2

    page_one_text = reader.pages[0].extract_text() or ""
    page_two_text = reader.pages[1].extract_text() or ""

    assert "Erster Absatz mit dem Aufhänger." in page_one_text
    assert "PROFIL" not in page_one_text

    assert cv_master.person.name in page_two_text
    assert "Erster Absatz mit dem Aufhänger." not in page_two_text
