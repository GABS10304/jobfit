"""Version 2 scenario tests: clear roles, ownership, remote, ranking, smoke."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend import data_loader, fit_engine
from backend.fit_engine import role_rank_tier
from backend.main import app

# --- JD fixtures (realistic, no invented SoT) ---

CLEAR_PRODUCT_JD = """
Remote hybrid AI Product Manager. You own product ownership and the roadmap.
B2B SaaS / GovTech. Product discovery, requirements, stakeholder alignment,
data driven decisions, backlog prioritization with Engineering.
"""

CLEAR_COORD_JD = """
Remote Agile Project Lead. Coordinate delivery across teams, iterative delivery,
stakeholder management, prioritization, Jira and Confluence. Cross-functional
coordination between Engineering and Sales. No product ownership – schedule
and delivery focus.
"""

CLEAR_COACH_JD = """
Remote Agile Coach. Coach agile teams, facilitate retrospectives and workshops,
support agile transformation, leadership coaching, team development and
facilitation. Miro, Jira, Confluence.
"""

GRAY_JUNIOR_JD = """
Junior Product / Transformation Lead

Wir suchen eine Person für ein B2B-SaaS-/GovTech-Umfeld, die Produktanforderungen
aus Kundenfeedback, Support-Tickets und internen Stakeholdern zusammenführt,
priorisiert und gemeinsam mit Engineering umsetzt.

Aufgaben
- Kundenfeedback, Support-Signale und interne Anforderungen analysieren.
- Prioritäten mit Engineering, Delivery, Sales und Operations abstimmen.
- Produktentscheidungen verständlich dokumentieren.
- Kleine Prozess- und Zusammenarbeitsthemen verbessern.
- Produkt- und Transformationsaufgaben verbinden, ohne reine Coaching-Rolle zu sein.

Rahmen
- Remote-first.
- Bis zu 1 Tag pro Woche im Office ist möglich.
- Ownership ist bewusst nicht explizit formuliert.
- Die Rolle ist produktnah, aber auch koordinativ und transformativ.
"""

OWNERSHIP_UNCLEAR_JD = """
Remote-first B2B SaaS Rolle. Anforderungen aus Kundenfeedback strukturieren,
mit Engineering priorisieren und umsetzen. Produktnahe Koordination.
"""

OWNERSHIP_CLEAR_JD = """
Remote Product Manager with clear product ownership and roadmap responsibility.
B2B SaaS GovTech.
"""


def _client() -> TestClient:
    data_loader.clear_domain_cache()
    return TestClient(app)


def _ordered(body: dict) -> list[dict]:
    return body["results"] + body["excluded_roles"]


def test_v2_clear_product_role_proceeds_and_ranks_product_first():
    body = _client().post("/fit-check", json={"job_description": CLEAR_PRODUCT_JD}).json()
    assert body["status_flag"] == "proceed"
    assert body["verify_product_ownership"] is False
    ordered = _ordered(body)
    assert ordered
    assert role_rank_tier(ordered[0]["role_id"]) == 1


def test_v2_clear_coordination_role_ranks_coord_or_high_score():
    body = _client().post("/fit-check", json={"job_description": CLEAR_COORD_JD}).json()
    # "no product ownership" → ownership failed → no_go
    assert body["status_flag"] == "no_go"
    assert body["results"] == []


def test_v2_clear_coaching_role_verify_or_proceed_but_coach_competitive():
    body = _client().post("/fit-check", json={"job_description": CLEAR_COACH_JD}).json()
    # Remote + no clear product ownership cues → verify, scoring continues
    assert body["status_flag"] == "verify_product_ownership"
    ordered = _ordered(body)
    assert ordered
    # Top role should be coaching tier or at least agile_coach in top 3
    top3 = [r["role_id"] for r in ordered[:3]]
    assert "agile_coach" in top3 or "agile_transformation_consultant" in top3


def test_v2_ownership_clear_vs_unclear():
    clear = _client().post("/fit-check", json={"job_description": OWNERSHIP_CLEAR_JD}).json()
    unclear = _client().post(
        "/fit-check", json={"job_description": OWNERSHIP_UNCLEAR_JD}
    ).json()
    assert clear["status_flag"] == "proceed"
    assert clear["verify_product_ownership"] is False
    assert unclear["status_flag"] == "verify_product_ownership"
    assert unclear["verify_product_ownership"] is True
    assert _ordered(unclear)  # scoring continues


def test_v2_smoke_junior_gray_zone():
    """Smoke: Junior Product/Transformation Lead – V2 Qualitätsanker."""
    body = _client().post("/fit-check", json={"job_description": GRAY_JUNIOR_JD}).json()
    assert body["status_flag"] == "verify_product_ownership"
    assert body["verify_product_ownership"] is True

    hard = {h["id"]: h["status"] for h in body["constraint_check"]["hard_results"]}
    assert hard["remote_first_hybrid_ok"] == "passed"
    assert hard["product_ownership_required"] == "unclear"

    ordered = _ordered(body)
    assert len(ordered) >= 5
    # Top roles should be product-tier when scores are in band
    top4_tiers = [role_rank_tier(r["role_id"]) for r in ordered[:4]]
    assert top4_tiers.count(1) >= 2, f"Expected product bias in top4, got {ordered[:4]}"


def test_v2_regression_reference_senior_still_green():
    from pathlib import Path

    import yaml

    case_path = (
        Path(__file__).resolve().parent.parent
        / "domain"
        / "fixtures"
        / "ref_senior_product_transformation_lead_hybrid.yaml"
    )
    case = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    body = _client().post(
        "/fit-check", json={"job_description": case["job_description"]}
    ).json()
    exp = case["expected"]
    assert body["status_flag"] == exp["status_flag"]
    ordered = _ordered(body)
    top = [r["role_id"] for r in ordered[: len(exp["top_role_ids"])]]
    assert top == exp["top_role_ids"]


def test_v2_regression_reference_junior_smoke():
    from pathlib import Path

    import yaml

    case_path = (
        Path(__file__).resolve().parent.parent
        / "domain"
        / "fixtures"
        / "ref_junior_product_transformation_lead_remote_first.yaml"
    )
    case = yaml.safe_load(case_path.read_text(encoding="utf-8"))
    body = _client().post(
        "/fit-check", json={"job_description": case["job_description"]}
    ).json()
    exp = case["expected"]
    assert body["status_flag"] == exp["status_flag"]
    assert body["verify_product_ownership"] is exp["verify_product_ownership"]
    hard = {h["id"]: h["status"] for h in body["constraint_check"]["hard_results"]}
    for cid, status in exp["hard_constraints"].items():
        assert hard[cid] == status
    ordered = _ordered(body)
    assert ordered
    product_in_top4 = sum(1 for r in ordered[:4] if role_rank_tier(r["role_id"]) == 1)
    assert product_in_top4 >= exp["min_product_roles_in_top4"]
