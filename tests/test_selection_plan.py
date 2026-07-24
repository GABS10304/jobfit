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
    assert rules.limits.max_certifications == 6
    assert rules.evidence.min_strength_for_inclusion == "medium"
    assert "[TODO]" in rules.evidence.exclude_markers
    assert "CV-Varianten" in rules.evidence.exclude_markers
    assert rules.keyword_mirroring.no_invention is True
    assert "employments" in rules.section_order


def test_project_bullets_prefer_result_and_approach():
    cv = data_loader.load_cv_master()
    profile = data_loader.load_role_fit_profile()
    constraints = data_loader.load_constraints()
    rules = data_loader.load_cv_rules()
    fit = fit_engine.run_fit_check(FLEX_LIKE_JD, profile, constraints)
    plan = selection_plan(cv, profile, fit, FLEX_LIKE_JD, rules)

    for proj in plan.projects:
        master = next(p for p in cv.projects if p.id == proj.project_id)
        texts = [b.bullet_text for b in proj.bullets]
        if master.result and master.result in texts and master.problem in texts:
            assert texts.index(master.result) < texts.index(master.problem)
        if master.approach and master.approach in texts and master.problem in texts:
            assert texts.index(master.approach) < texts.index(master.problem)


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


AGILE_COACH_LIKE_JD = (
    "Remote-first Agile Coach / Scrum Master for B2B SaaS enterprise transformation. "
    "Team coaching, facilitation, retrospectives, leadership coaching, "
    "change management, workshop design, org design, agile coaching, "
    "stakeholder alignment, impediment removal, backlog refinement. "
    "Coaching mandate is primary."
)


def _employment_titles(plan, cv) -> list[str]:
    by_id = {e.id: e for e in cv.employments}
    return [by_id[eid].role_title for eid in plan.selected_employment_ids]


def test_employment_ranking_ai_pm_prefers_product_over_scrum():
    """AI/Product PM JD: Product/AI stations dominate; Scrum Master not first."""
    cv = data_loader.load_cv_master()
    profile = data_loader.load_role_fit_profile()
    constraints = data_loader.load_constraints()
    rules = data_loader.load_cv_rules()

    fit = fit_engine.run_fit_check(FLEX_LIKE_JD, profile, constraints)
    plan = selection_plan(cv, profile, fit, FLEX_LIKE_JD, rules)

    assert plan.selected_role_id in (
        "ai_product_manager",
        "technical_product_manager",
        "product_transformation_lead",
        "b2b_saas_govtech_product_lead",
    )
    titles = _employment_titles(plan, cv)
    assert titles, "expected selected employments"
    assert "Scrum Master" not in titles[0]
    assert any("Product Manager" in t for t in titles[:2])

    ids = plan.selected_employment_ids
    assert "st-01-riwa" in ids
    if "st-03-jtl" in ids and "st-04-gbs" in ids:
        assert ids.index("st-04-gbs") < ids.index("st-03-jtl")


def test_employment_ranking_agile_coach_lifts_coaching_stations():
    """Coaching-heavy JD: Scrum/coaching stations rise vs AI-PM ordering."""
    cv = data_loader.load_cv_master()
    profile = data_loader.load_role_fit_profile()
    constraints = data_loader.load_constraints()
    rules = data_loader.load_cv_rules()

    fit_pm = fit_engine.run_fit_check(FLEX_LIKE_JD, profile, constraints)
    plan_pm = selection_plan(cv, profile, fit_pm, FLEX_LIKE_JD, rules)

    fit_coach = fit_engine.run_fit_check(AGILE_COACH_LIKE_JD, profile, constraints)
    plan_coach = selection_plan(cv, profile, fit_coach, AGILE_COACH_LIKE_JD, rules)

    assert plan_coach.selected_role_id in (
        "agile_coach",
        "scrum_master",
        "agile_transformation_consultant",
    )

    coach_ids = plan_coach.selected_employment_ids
    assert "st-03-jtl" in coach_ids

    # Relative to AI-PM plan: JTL should rank higher (lower index) under coaching JD.
    if "st-03-jtl" in plan_pm.selected_employment_ids:
        assert coach_ids.index("st-03-jtl") < plan_pm.selected_employment_ids.index(
            "st-03-jtl"
        )

    # Coaching station should outrank product-leaning GBS when both present.
    if "st-03-jtl" in coach_ids and "st-04-gbs" in coach_ids:
        assert coach_ids.index("st-03-jtl") < coach_ids.index("st-04-gbs")
