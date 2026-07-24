"""Tests for ATS-friendly CV text rendering from SelectionPlan."""

from __future__ import annotations

from backend import data_loader, fit_engine
from backend.generation.cv_variant import generate_cv_variant
from backend.generation.selection_plan import selection_plan

FLEX_LIKE_JD = (
    "Remote / hybrid AI Product Manager for B2B SaaS. "
    "Product ownership, product discovery, AI use case validation, "
    "customer feedback, stakeholder management, change management, "
    "requirements engineering, data driven decision making. "
    "Stack: Python, SQL, Jira, Confluence."
)


def _plan_and_render():
    cv = data_loader.load_cv_master()
    profile = data_loader.load_role_fit_profile()
    constraints = data_loader.load_constraints()
    rules = data_loader.load_cv_rules()
    fit = fit_engine.run_fit_check(FLEX_LIKE_JD, profile, constraints)
    plan = selection_plan(cv, profile, fit, FLEX_LIKE_JD, rules)
    text = generate_cv_variant(plan, cv, rules)
    return plan, cv, rules, text


def test_render_contains_section_headers():
    _plan, _cv, rules, text = _plan_and_render()
    assert "## Profil" in text
    assert "## Berufserfahrung" in text
    assert "## Projekte" in text
    assert "## Kompetenzen" in text
    assert "## Tools" in text
    assert "## Zertifizierungen" in text
    # section_order starts with profile after header
    assert rules.section_order[0] == "profile"
    assert text.index("## Profil") < text.index("## Berufserfahrung")
    assert text.index("## Berufserfahrung") < text.index("## Projekte")


def test_render_includes_selected_bullets_only():
    from backend.generation.cv_variant import _ats_bullet_text

    plan, cv, _rules, text = _plan_and_render()
    assert cv.person.name in text

    for emp in plan.employments:
        master = next(e for e in cv.employments if e.id == emp.employment_id)
        assert master.company in text
        assert master.role_title in text
        for bullet in emp.bullets:
            assert _ats_bullet_text(bullet.bullet_text) in text

    for proj in plan.projects:
        master = next(p for p in cv.projects if p.id == proj.project_id)
        assert master.title in text
        for bullet in proj.bullets:
            assert _ats_bullet_text(bullet.bullet_text) in text


def test_render_excludes_todo_markers():
    _plan, _cv, _rules, text = _plan_and_render()
    assert "[TODO]" not in text
    assert "[belegt]" not in text
    assert "[teilweise belegt]" not in text
    assert "[qualitativ belegt]" not in text


def test_render_deterministic():
    plan, cv, rules, text_a = _plan_and_render()
    text_b = generate_cv_variant(plan, cv, rules)
    assert text_a == text_b


def test_render_uses_role_based_profile_not_invented_claims():
    plan, cv, rules, text = _plan_and_render()
    assert plan.selected_role_name in text or plan.selected_role_id in text
    # Profile uses master kernel when present – no free-form invention block.
    if cv.person.profile_kernel:
        kernel = cv.person.profile_kernel.strip()
        capitalized = kernel[0].upper() + kernel[1:]
        assert capitalized in text or kernel in text
    assert "Ausrichtung:" in text


def test_render_excludes_meta_documentation_bullets():
    _plan, _cv, _rules, text = _plan_and_render()
    assert "CV-Varianten" not in text
    assert "Original-CV" not in text