"""Smoke tests for domain loading, constraints, /health, and /fit-check."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import constraints_engine, data_loader, fit_engine
from backend.main import app
from backend.models import RoleFitProfile, RoleFitResult, RoleSignals

REPO_ROOT = Path(__file__).resolve().parent.parent
DOMAIN = REPO_ROOT / "domain"

# JD that passes hard gates and scores well for ai_product_manager.
GOOD_JD = (
    "Remote / hybrid role: AI Product Manager for B2B SaaS in GovTech "
    "and regulated environments. You own product ownership and the roadmap. "
    "Focus: product discovery, AI use case validation, MVP validation, "
    "data driven decision making, stakeholder communication, product analytics, "
    "requirements engineering, experimental validation, privacy by design, "
    "enterprise software, customer intelligence. "
    "Stack: SQL, Python, pandas, Streamlit, LangChain, Ollama, BigQuery, MCP, "
    "Claude Desktop, Jira Product Discovery. Agile transformation experience welcome."
)


@pytest.fixture
def client() -> TestClient:
    data_loader.clear_domain_cache()
    return TestClient(app)


def test_load_cv_master():
    cv = data_loader.load_cv_master(DOMAIN / "cv_master.yaml")
    assert cv.person.name == "Gabriel Strecker"
    assert len(cv.employments) >= 6
    assert len(cv.projects) >= 6
    assert cv.employments[0].role_title
    assert "RIWA" in cv.employments[0].company or cv.employments[0].id.startswith("st-01")
    assert cv.skills
    assert cv.tools
    assert cv.certifications
    assert cv.open_todos


def test_cv_master_yaml_json_parity():
    data_loader.assert_cv_master_parity()
    from_json = data_loader.load_cv_master_json()
    assert from_json.person.name == "Gabriel Strecker"


def test_load_role_fit_profile():
    profile = data_loader.load_role_fit_profile(DOMAIN / "role_fit_profile.yaml")
    assert len(profile.roles) >= 10
    assert profile.roles[0].role_id == "ai_product_manager"
    assert profile.roles[0].core_signals_skills
    assert profile.roles[0].match_patterns_positive


def test_load_constraints():
    constraints = data_loader.load_constraints(DOMAIN / "constraints.yaml")
    assert len(constraints.hard_constraints) == 3
    assert constraints.application_rules.min_score_for_review == 75
    assert {c.id for c in constraints.hard_constraints} == {
        "remote_first_hybrid_ok",
        "no_hard_sales",
        "product_ownership_required",
    }


def test_constraints_remote_unclear_is_no_go():
    constraints = data_loader.load_constraints()
    result = constraints_engine.evaluate_constraints(
        "Office-based Product Manager role with product ownership.",
        constraints,
    )
    assert result.decision == "no_go"
    remote = next(r for r in result.hard_results if r.id == "remote_first_hybrid_ok")
    assert remote.status == "unclear"


def test_constraints_remote_first_one_office_day_per_week_passes():
    """Remote-first mit bis zu 1 Office-Tag/Woche ohne 'hybrid'-Wort → passed."""
    constraints = data_loader.load_constraints()
    result = constraints_engine.evaluate_constraints(
        "Remote-first Position. Bis zu 1 Tag pro Woche im Office ist möglich. "
        "Product Manager with product ownership.",
        constraints,
    )
    remote = next(r for r in result.hard_results if r.id == "remote_first_hybrid_ok")
    assert remote.status == "passed"
    assert result.decision == "proceed"


def test_constraints_two_office_days_is_penalty_not_hard_fail():
    """V3: 2–3 Office-Tage = Penalty (Scoring + Ausnahme), nicht sofort no_go."""
    constraints = data_loader.load_constraints()
    result = constraints_engine.evaluate_constraints(
        "2 Präsenztage im Büro. Product Manager with ownership.",
        constraints,
    )
    assert result.decision == "proceed"
    assert result.presence_requires_exception is True
    remote = next(r for r in result.hard_results if r.id == "remote_first_hybrid_ok")
    assert remote.status == "penalty"


def test_constraints_hard_presence_pflicht_is_no_go():
    """V3: feste Präsenzpflicht / überwiegend vor Ort = hartes No-Go."""
    constraints = data_loader.load_constraints()
    result = constraints_engine.evaluate_constraints(
        "Feste Präsenzpflicht, überwiegend vor Ort. Product Manager.",
        constraints,
    )
    assert result.decision == "no_go"
    remote = next(r for r in result.hard_results if r.id == "remote_first_hybrid_ok")
    assert remote.status == "failed"


def test_constraints_four_office_days_is_no_go():
    """V3: >3 Office-Tage = hartes No-Go."""
    constraints = data_loader.load_constraints()
    result = constraints_engine.evaluate_constraints(
        "4 Präsenztage pro Woche im Büro. Product Manager with ownership.",
        constraints,
    )
    assert result.decision == "no_go"
    remote = next(r for r in result.hard_results if r.id == "remote_first_hybrid_ok")
    assert remote.status == "failed"


def test_soft_coaching_not_matched_on_negated_phrase():
    """„ohne reine Coaching-Rolle“ darf team_coaching_preferred nicht triggern."""
    constraints = data_loader.load_constraints()
    result = constraints_engine.evaluate_constraints(
        "Remote hybrid Product Manager with product ownership. "
        "Kleine Transformationen begleiten, ohne reine Coaching-Rolle zu sein.",
        constraints,
    )
    coaching = next(r for r in result.soft_results if r.id == "team_coaching_preferred")
    assert coaching.status == "not_matched"


def test_constraints_hard_sales_fails():
    constraints = data_loader.load_constraints()
    result = constraints_engine.evaluate_constraints(
        "Remote Account Executive with quota and cold calling. Hunter role.",
        constraints,
    )
    assert result.decision == "no_go"
    assert result.verify_product_ownership is False
    sales = next(r for r in result.hard_results if r.id == "no_hard_sales")
    assert sales.status == "failed"


def test_constraints_product_ownership_unclear_is_verify_not_no_go():
    constraints = data_loader.load_constraints()
    result = constraints_engine.evaluate_constraints(
        "Remote hybrid role for a delivery-focused team in B2B SaaS. "
        "Coordinate across engineering and stakeholders.",
        constraints,
    )
    assert result.decision == "verify_product_ownership"
    assert result.verify_product_ownership is True
    ownership = next(
        r for r in result.hard_results if r.id == "product_ownership_required"
    )
    assert ownership.status == "unclear"


def test_constraints_product_ownership_clear_is_proceed():
    constraints = data_loader.load_constraints()
    result = constraints_engine.evaluate_constraints(
        "Remote AI Product Manager with product ownership and roadmap.",
        constraints,
    )
    assert result.decision == "proceed"
    assert result.verify_product_ownership is False
    ownership = next(
        r for r in result.hard_results if r.id == "product_ownership_required"
    )
    assert ownership.status == "passed"


def test_constraints_non_product_role_is_no_go():
    constraints = data_loader.load_constraints()
    result = constraints_engine.evaluate_constraints(
        "Remote pure project manager / admin PMO role with no product ownership.",
        constraints,
    )
    assert result.decision == "no_go"
    ownership = next(
        r for r in result.hard_results if r.id == "product_ownership_required"
    )
    assert ownership.status == "failed"


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_fit_check_with_dummy_jd(client: TestClient):
    response = client.post(
        "/fit-check",
        json={"job_description": GOOD_JD, "role_ids": ["ai_product_manager"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert "job_description_snippet" in body
    assert body["constraint_check"]["decision"] == "proceed"
    assert body["constraint_check"]["verify_product_ownership"] is False
    assert body["status_flag"] == "proceed"
    assert body["verify_product_ownership"] is False
    assert len(body["results"]) == 1
    result = body["results"][0]
    assert result["role_id"] == "ai_product_manager"
    assert 0 <= result["score"] <= 100
    assert result["score"] >= 75
    assert result["passes_review_threshold"] is True
    assert isinstance(result["matched_signals"], list)
    assert isinstance(result["missing_signals"], list)
    assert result["reason"]


def test_fit_check_verify_product_ownership_still_scores(client: TestClient):
    jd = (
        "Remote / hybrid B2B SaaS role in GovTech and regulated environments. "
        "Focus: product discovery, AI use case validation, MVP validation, "
        "data driven decision making, stakeholder communication, product analytics, "
        "requirements engineering, experimental validation, privacy by design, "
        "enterprise software, customer intelligence. "
        "Stack: SQL, Python, pandas, Streamlit, LangChain, Ollama, BigQuery, MCP, "
        "Claude Desktop, Jira Product Discovery."
    )
    response = client.post(
        "/fit-check",
        json={"job_description": jd, "role_ids": ["ai_product_manager"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["constraint_check"]["decision"] == "verify_product_ownership"
    assert body["constraint_check"]["verify_product_ownership"] is True
    assert body["status_flag"] == "verify_product_ownership"
    assert body["verify_product_ownership"] is True
    assert len(body["results"]) == 1
    assert body["results"][0]["role_id"] == "ai_product_manager"
    assert body["results"][0]["score"] >= 75


def test_fit_check_no_go_skips_roles(client: TestClient):
    response = client.post(
        "/fit-check",
        json={
            "job_description": "Onsite only office role. No remote. Pure quota hunter sales.",
            "role_ids": ["ai_product_manager"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["constraint_check"]["decision"] == "no_go"
    assert body["constraint_check"]["verify_product_ownership"] is False
    assert body["status_flag"] == "no_go"
    assert body["verify_product_ownership"] is False
    assert body["results"] == []


def test_fit_check_german_gray_zone_verify_ownership(client: TestClient):
    """Smoke: produktnahe Grauzonen-JD mit unklarer Ownership.

    Erwartungen (docs/SMOKE_TEST.md):
    1) status_flag = verify_product_ownership
    2) verify = true
    3) Scoring läuft weiter
    4) Produktrollen vor Koordination/Coaching bei ähnlichen Scores
    5) Top-Reihenfolge nicht rein numerisch (Tier greift)
    """
    jd = (
        "Remote / Deutschland. Wir suchen Verstärkung für unsere B2B-SaaS-Plattform. "
        "Du nimmst Anforderungen aus Markt und Kundenfeedback auf, strukturierst sie, "
        "priorisierst das Backlog gemeinsam mit Stakeholdern und stimmst dich mit "
        "Engineering, UX und Vertrieb ab. Produktkennzahlen und Reporting fließen in "
        "Handlungsempfehlungen ein. Erfahrung mit Jira, Confluence, agilen Methoden "
        "und datengetriebenen Entscheidungen. GovTech oder Enterprise Software von Vorteil."
    )
    response = client.post("/fit-check", json={"job_description": jd})
    assert response.status_code == 200
    body = response.json()

    assert body["status_flag"] == "verify_product_ownership"
    assert body["verify_product_ownership"] is True

    ordered = body["results"] + body["excluded_roles"]
    assert ordered, "Scoring muss trotz verify weiterlaufen"
    assert all("reason" in r for r in ordered)

    from backend.fit_engine import ROLE_RANK_TIER, SIMILAR_SCORE_BAND, role_rank_tier

    # Erwartung 4/5: keine Koordinations-/Coaching-Rolle vor einer Produktrolle,
    # wenn der Score-Vorsprung innerhalb des Bands liegt.
    product_ids = {rid for rid, t in ROLE_RANK_TIER.items() if t == 1}
    for i, lower in enumerate(ordered):
        for higher in ordered[:i]:
            if (
                role_rank_tier(lower["role_id"]) == 1
                and role_rank_tier(higher["role_id"]) > 1
            ):
                gap = higher["score"] - lower["score"]
                max_gap = (role_rank_tier(higher["role_id"]) - 1) * SIMILAR_SCORE_BAND
                assert gap > max_gap, (
                    f"{higher['role_id']} ({higher['score']}) steht vor "
                    f"{lower['role_id']} ({lower['score']}), obwohl Gap {gap} "
                    f"≤ Band-Schwelle {max_gap}"
                )

    # Mindestens eine Produktrolle in den Top 5 (fachliche Plausibilität)
    top5 = {r["role_id"] for r in ordered[:5]}
    assert top5 & product_ids, f"Top-5 ohne Produktrolle: {ordered[:5]}"


def test_smoke_no_regression_clear_product_and_non_product(client: TestClient):
    """Akzeptanz: klare Produkt-JD → proceed; Nicht-Produkt → no_go."""
    clear_product = (
        "Remote hybrid AI Product Manager with product ownership and roadmap. "
        "B2B SaaS, GovTech, product discovery, data driven decision making."
    )
    r1 = client.post("/fit-check", json={"job_description": clear_product}).json()
    assert r1["status_flag"] == "proceed"
    assert r1["verify_product_ownership"] is False

    non_product = (
        "Remote pure project manager / admin PMO role with no product ownership."
    )
    r2 = client.post("/fit-check", json={"job_description": non_product}).json()
    assert r2["status_flag"] == "no_go"
    assert r2["results"] == []
    assert r2["excluded_roles"] == []


def test_fit_engine_unit_dummy_profile():
    profile = RoleFitProfile(
        roles=[
            RoleSignals(
                role_id="demo_role",
                role_name="Demo",
                core_signals_skills=["python", "fastapi"],
                core_signals_domains=["backend"],
                core_signals_tools=["pytest"],
            )
        ]
    )
    results = fit_engine.fit_check(
        "We use Python and FastAPI for backend services with pytest.",
        profile,
    )
    assert results[0].score == 100
    assert set(results[0].matched_signals) == {
        "python",
        "fastapi",
        "backend",
        "pytest",
    }
    assert results[0].missing_signals == []


def test_role_ranking_prefers_product_ownership_on_similar_scores():
    ranked = fit_engine.rank_roles(
        [
            RoleFitResult(
                role_id="agile_coach",
                role_name="Agile Coach",
                score=70,
                matched_signals=[],
                missing_signals=[],
            ),
            RoleFitResult(
                role_id="ai_product_manager",
                role_name="AI PM",
                score=68,
                matched_signals=[],
                missing_signals=[],
            ),
            RoleFitResult(
                role_id="product_operations",
                role_name="Product Ops",
                score=69,
                matched_signals=[],
                missing_signals=[],
            ),
        ]
    )
    # Ähnliche Scores → Tier 1 vor Tier 2 vor Tier 3
    assert [r.role_id for r in ranked] == [
        "ai_product_manager",
        "product_operations",
        "agile_coach",
    ]


def test_role_ranking_product_beats_coordination_when_slightly_lower():
    """Grauzone: Produkt 50 vs Koordination 57 → Produkt zuerst (Band=12)."""
    ranked = fit_engine.rank_roles(
        [
            RoleFitResult(
                role_id="scrum_master",
                role_name="SM",
                score=57,
                matched_signals=[],
                missing_signals=[],
            ),
            RoleFitResult(
                role_id="technical_product_manager",
                role_name="TPM",
                score=50,
                matched_signals=[],
                missing_signals=[],
            ),
            RoleFitResult(
                role_id="client_solutions_lead",
                role_name="CSL",
                score=56,
                matched_signals=[],
                missing_signals=[],
            ),
        ]
    )
    assert ranked[0].role_id == "technical_product_manager"
    assert [r.role_id for r in ranked[1:]] == [
        "scrum_master",
        "client_solutions_lead",
    ]


def test_role_ranking_large_score_gap_still_wins():
    ranked = fit_engine.rank_roles(
        [
            RoleFitResult(
                role_id="ai_product_manager",
                role_name="AI PM",
                score=40,
                matched_signals=[],
                missing_signals=[],
            ),
            RoleFitResult(
                role_id="agile_project_lead",
                role_name="APL",
                score=71,
                matched_signals=[],
                missing_signals=[],
            ),
        ]
    )
    assert ranked[0].role_id == "agile_project_lead"
    assert ranked[1].role_id == "ai_product_manager"


def _rr(role_id: str, score: int) -> RoleFitResult:
    return RoleFitResult(
        role_id=role_id,
        role_name=role_id,
        score=score,
        matched_signals=[],
        missing_signals=[],
    )


def test_band12_coord_just_inside_still_loses_to_product():
    """Koordination = Produkt + (BAND-1) → Produkt bleibt vorn."""
    band = fit_engine.SIMILAR_SCORE_BAND
    assert band == 12
    product = _rr("ai_product_manager", 50)
    coord = _rr("scrum_master", 50 + band - 1)  # 61
    ranked = fit_engine.rank_roles([coord, product])
    assert [r.role_id for r in ranked] == [
        "ai_product_manager",
        "scrum_master",
    ]


def test_band12_coord_exact_boundary_tie_goes_to_product():
    """Koordination = Produkt + BAND → adjusted gleich → Tier bricht zugunsten Produkt."""
    band = fit_engine.SIMILAR_SCORE_BAND
    product = _rr("technical_product_manager", 50)
    coord = _rr("product_operations", 50 + band)  # 62
    ranked = fit_engine.rank_roles([coord, product])
    assert ranked[0].role_id == "technical_product_manager"
    assert ranked[1].role_id == "product_operations"


def test_band12_coord_just_outside_beats_product():
    """Koordination = Produkt + BAND + 1 → deutlicher Vorsprung, Koordination vorn."""
    band = fit_engine.SIMILAR_SCORE_BAND
    product = _rr("b2b_saas_govtech_product_lead", 50)
    coord = _rr("agile_project_lead", 50 + band + 1)  # 63
    ranked = fit_engine.rank_roles([product, coord])
    assert [r.role_id for r in ranked] == [
        "agile_project_lead",
        "b2b_saas_govtech_product_lead",
    ]


def test_band12_coach_needs_double_band_to_beat_product():
    """Coaching braucht > 2*BAND Vorsprung gegen Produkt; genau 2*BAND → Produkt."""
    band = fit_engine.SIMILAR_SCORE_BAND
    product = _rr("product_transformation_lead", 50)
    coach_tie = _rr("agile_coach", 50 + 2 * band)  # 74 → adjusted 50
    coach_win = _rr("agile_transformation_consultant", 50 + 2 * band + 1)  # 75

    ranked_tie = fit_engine.rank_roles([coach_tie, product])
    assert ranked_tie[0].role_id == "product_transformation_lead"

    ranked_win = fit_engine.rank_roles([coach_win, product])
    assert ranked_win[0].role_id == "agile_transformation_consultant"


def test_german_synonym_matching_for_core_pm_signals():
    """German JD phrases should match English snake_case signal ids via lexicon."""
    profile = RoleFitProfile(
        roles=[
            RoleSignals(
                role_id="pm_demo",
                role_name="PM Demo",
                core_signals_skills=[
                    "product_discovery",
                    "ai_use_case_validation",
                    "data_driven_decision_making",
                    "stakeholder_communication",
                    "requirements_engineering",
                    "technical_product_management",
                    "agile_coaching",
                    "organizational_diagnostics",
                    "product_operations",
                ],
                core_signals_domains=["b2b_saas", "platform_products"],
                core_signals_tools=["jira"],
            )
        ]
    )
    jd = (
        "Remote Product Manager: Anforderungsanalyse, Produktvision, Priorisierung, "
        "Produktentwicklung, Backlog und Roadmap. "
        "AI-Use-Case Verprobung mit Pilotkunden, Prototyp und Machbarkeit/Validierung. "
        "datengetriebenen Entscheidungen, Kennzahlen, Analysen, Reporting, Dashboard. "
        "Abstimmung und Alignment mit Stakeholdern, Koordination und Moderation. "
        "Anforderungen strukturieren, Spezifikation, User Story und Story Writing. "
        "technische Anschlussfähigkeit, Engineering, Architektur, Prototyping. "
        "Coaching, Teamentwicklung, Facilitation, Workshops, Retrospektive, Teamreife. "
        "Diagnose und Organisationsanalyse, Reality Gap, Operating Model, Teamzustand. "
        "Priorisierungssystem, Portfolio, Operating Rhythm, Discovery Backbone, Governance. "
        "B2B-Software und Plattform-Software. Erfahrung mit Jira."
    )
    results = fit_engine.fit_check(jd, profile, min_score_for_review=0)
    assert results[0].missing_signals == []
    assert results[0].score == 100


def test_fit_check_unknown_role(client: TestClient):
    response = client.post(
        "/fit-check",
        json={
            "job_description": GOOD_JD,
            "role_ids": ["does_not_exist"],
        },
    )
    assert response.status_code == 400
