"""Unit tests for deterministic CV selection_plan (Phase 2) – V3 untouched."""

from __future__ import annotations

from pathlib import Path

import yaml

from backend import data_loader, fit_engine
from backend.generation.selection_plan import selection_plan
from backend.models import CvVariant

REPO_ROOT = Path(__file__).resolve().parent.parent
TEAMVIEWER_FIXTURE = (
    REPO_ROOT
    / "domain"
    / "fixtures"
    / "ops_teamviewer_ai_product_discovery_hybrid.yaml"
)

FLEX_LIKE_JD = (
    "Remote / hybrid AI Product Manager for B2B SaaS. "
    "Product ownership, product discovery, AI use case validation, "
    "customer feedback, stakeholder management, change management, "
    "requirements engineering, data driven decision making. "
    "Stack: Python, SQL, Jira, Confluence."
)


def _jd_from_fixture(path: Path) -> str:
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return str(raw["job_description"])


def test_load_cv_rules():
    rules = data_loader.load_cv_rules()
    assert rules.language.default == "de"
    assert rules.limits.max_bullets_per_employment == 5
    assert rules.evidence.min_strength_for_inclusion == "medium"
    assert "[TODO]" in rules.evidence.exclude_markers
    assert "CV-Varianten" in rules.evidence.exclude_markers
    assert rules.keyword_mirroring.no_invention is True
    assert "employments" in rules.section_order


def test_selection_plan_deterministic_flex_like_jd():
    cv = data_loader.load_cv_master()
    profile = data_loader.load_role_fit_profile()
    constraints = data_loader.load_constraints()
    rules = data_loader.load_cv_rules()

    fit = fit_engine.run_fit_check(FLEX_LIKE_JD, profile, constraints)
    plan_a = selection_plan(cv, profile, fit, FLEX_LIKE_JD, rules)
    plan_b = selection_plan(cv, profile, fit, FLEX_LIKE_JD, rules)

    assert plan_a.model_dump() == plan_b.model_dump()
    assert plan_a.selected_role_id
    assert plan_a.role_source in ("results", "excluded_roles")
    assert len(plan_a.selected_employment_ids) <= rules.limits.max_employments
    assert len(plan_a.selected_project_ids) <= rules.limits.max_projects
    for emp in plan_a.employments:
        assert len(emp.bullets) <= rules.limits.max_bullets_per_employment
        for bullet in emp.bullets:
            assert "[TODO]" not in bullet.bullet_text
    for proj in plan_a.projects:
        assert len(proj.bullets) <= rules.limits.max_bullets_per_project

    # Prefer projects that support the selected role when available.
    supporting = [
        p.id
        for p in cv.projects
        if plan_a.selected_role_id in p.supports_roles
    ]
    if supporting:
        assert any(
            pid in supporting for pid in plan_a.selected_project_ids
        ), plan_a.selected_project_ids


def test_selection_plan_teamviewer_fixture():
    """Uses existing TeamViewer fixture JD (FLEX-like product/discovery case)."""
    assert TEAMVIEWER_FIXTURE.exists()
    jd = _jd_from_fixture(TEAMVIEWER_FIXTURE)
    cv = data_loader.load_cv_master()
    profile = data_loader.load_role_fit_profile()
    constraints = data_loader.load_constraints()
    rules = data_loader.load_cv_rules()

    fit = fit_engine.run_fit_check(jd, profile, constraints)
    plan = selection_plan(cv, profile, fit, jd, rules)

    assert plan.selected_role_id
    # TeamViewer fixture: scores often below review → excluded_roles path ok.
    assert plan.role_source in ("results", "excluded_roles")
    assert plan.explain.get("language") == "de"
    assert plan.rationale

    variant = CvVariant(
        selection_plan=plan,
        language=rules.language.default,
        section_order=list(rules.section_order),
        max_pages_hint=rules.limits.max_total_pages_hint,
    )
    assert variant.max_pages_hint == 2
    assert "projects" in variant.section_order


def test_selection_plan_excludes_todo_bullets():
    cv = data_loader.load_cv_master()
    profile = data_loader.load_role_fit_profile()
    constraints = data_loader.load_constraints()
    rules = data_loader.load_cv_rules()
    fit = fit_engine.run_fit_check(FLEX_LIKE_JD, profile, constraints)
    plan = selection_plan(cv, profile, fit, FLEX_LIKE_JD, rules)

    all_texts = [
        b.bullet_text
        for emp in plan.employments
        for b in emp.bullets
    ] + [
        b.bullet_text
        for proj in plan.projects
        for b in proj.bullets
    ]
    assert all("[TODO]" not in t for t in all_texts)
    assert all("CV-Varianten" not in t for t in all_texts)
    assert all("Original-CV" not in t for t in all_texts)
