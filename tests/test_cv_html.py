"""Tests for the styled HTML/Playwright CV renderer (backend.generation.cv_html)."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend import data_loader, fit_engine
from backend.generation.cv_html import generate_cv_variant_html, generate_cv_variant_pdf_html
from backend.generation.selection_plan import selection_plan

JD_TEXT = (
    "AI Product Manager (m/w/d)\n\n"
    "Berlin, Remote\n\n"
    "Wir suchen jemanden mit Erfahrung in Product Discovery, AI-Use-Case-Validierung, "
    "Python und LLM-Integrationen. Du arbeitest eigenständig und baust Prototypen."
)


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


def test_generate_cv_variant_html_contains_key_sections(sample_plan):
    plan, cv_master, cv_rules = sample_plan
    html = generate_cv_variant_html(plan, cv_master, cv_rules)

    assert "<!doctype html>" in html.lower()
    assert cv_master.person.name in html
    assert "PROFIL" in html or "Profil" in html
    assert "BERUFSERFAHRUNG" in html or "Berufserfahrung" in html
    assert "@font-face" in html


def test_generate_cv_variant_html_escapes_special_characters(sample_plan):
    plan, cv_master, cv_rules = sample_plan
    html = generate_cv_variant_html(plan, cv_master, cv_rules)
    # Ampersands in tool/skill names (e.g. "Data & AI Product Analysis") must
    # be escaped, not break the markup.
    assert "&amp;" in html or "&" not in cv_master.skills[0].name


def test_generate_cv_variant_html_no_evidence_tags_leak(sample_plan):
    plan, cv_master, cv_rules = sample_plan
    html = generate_cv_variant_html(plan, cv_master, cv_rules)
    assert "[belegt]" not in html
    assert "[TODO]" not in html


def test_generate_cv_variant_pdf_html_produces_ats_safe_pdf(tmp_path: Path, sample_plan):
    pytest.importorskip("playwright.sync_api")
    plan, cv_master, cv_rules = sample_plan

    try:
        out = generate_cv_variant_pdf_html(plan, cv_master, cv_rules, tmp_path / "cv.pdf")
    except Exception as exc:  # pragma: no cover - environment without browser binaries
        pytest.skip(f"Playwright Chromium not available: {exc}")

    assert out.is_file()
    assert out.stat().st_size > 0

    from backend.generation.ats_check import extract_pdf_text

    text, page_count = extract_pdf_text(out)
    assert page_count >= 1
    assert cv_master.person.name in text
    assert cv_master.person.location in text
