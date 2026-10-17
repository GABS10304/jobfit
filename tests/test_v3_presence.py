"""V3: Präsenz als Penalty – Boundary-Tests + Grauzonen-Smoke."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend import constraints_engine, data_loader
from backend.main import app
from backend.models import PresencePolicyResult
from tests._strict_presence import strict_presence  # noqa: F401  (autouse: V3 strict policy)

# Starke Produkt-JD – erwartet Score ≥ 90 für ai_product_manager.
STRONG_PRODUCT_JD_BODY = (
    "AI Product Manager for B2B SaaS in GovTech "
    "and regulated environments. You own product ownership and the roadmap. "
    "Focus: product discovery, AI use case validation, MVP validation, "
    "data driven decision making, stakeholder communication, product analytics, "
    "requirements engineering, experimental validation, privacy by design, "
    "enterprise software, customer intelligence. "
    "Stack: SQL, Python, pandas, Streamlit, LangChain, Ollama, BigQuery, MCP, "
    "Claude Desktop, Jira Product Discovery."
)

WEAK_PRODUCT_JD = (
    "2 Präsenztage im Büro. Product Manager with product ownership. "
    "B2B SaaS focus, some stakeholder communication."
)

# Echte Grauzone: 2 Office-Tage als Trade-off, keine absolute Präsenzpflicht.
GRAYZONE_PRESENCE_TRADEOFF_JD = """
Product / Transformation Lead (Hybrid-Trade-off)

Wir suchen Verstärkung für unsere B2B-SaaS-Plattform im GovTech- und
regulierten Umfeld. Du hast product ownership und gestaltest die Roadmap.

Aufgaben
- Product Discovery und AI Use Case Validation mit Pilotkunden.
- MVP Validation, experimental validation und datengetriebene Entscheidungen.
- Stakeholder Communication mit Engineering, UX und Fachbereichen.
- Product Analytics, Requirements Engineering, Privacy by Design.
- Enterprise Software und Customer Intelligence.

Stack
SQL, Python, pandas, Streamlit, LangChain, Ollama, BigQuery, MCP,
Claude Desktop, Jira Product Discovery.

Arbeitsmodell (Trade-off, keine absolute Pflicht)
- Remote-first ist möglich.
- In der Regel erwarten wir 2 Tage pro Woche im Office für Workshops
  und Stakeholder-Abstimmung.
- Keine feste Präsenzpflicht: der Mix ist verhandelbar, wenn der
  Gesamtnutzen und der Rollenfit klar überwiegen.
"""


@pytest.fixture
def client() -> TestClient:
    data_loader.clear_domain_cache()
    return TestClient(app)


# --- Boundary: 1 / 2 / 3 / >3 Office-Tage (Constraint-Layer) ---


@pytest.mark.parametrize(
    ("presence_phrase", "expected_status", "requires_exception"),
    [
        ("Bis zu 1 Tag pro Woche im Office.", "passed", False),
        ("2 Präsenztage pro Woche im Büro.", "penalty", True),
        ("3 Präsenztage pro Woche im Büro.", "penalty", True),
        ("4 Präsenztage pro Woche im Büro.", "failed", False),
        # sipgate-style: frequency without "Tage"; hyphen + en-dash
        ("Lust 2-3 Mal die Woche an unseren Campus zu kommen.", "penalty", True),
        ("Lust, 2–3 Mal die Woche an unseren Campus zu kommen.", "penalty", True),
        ("gerne 2 bis 3 Tage pro Woche bei uns am Campus.", "penalty", True),
    ],
    ids=[
        "1_day_ok",
        "2_days_penalty",
        "3_days_penalty",
        "gt3_days_no_go",
        "mal_die_woche_hyphen",
        "mal_die_woche_en_dash",
        "bis_tage_pro_woche",
    ],
)
def test_v3_boundary_office_days_constraint_layer(
    presence_phrase: str, expected_status: str, requires_exception: bool
):
    constraints = data_loader.load_constraints()
    jd = (
        f"{presence_phrase} Product Manager with product ownership and roadmap. "
        "Remote möglich."
    )
    # >3: "remote" allein darf Hard-Fail nicht aufheben.
    if expected_status == "failed":
        jd = f"{presence_phrase} Product Manager with product ownership and roadmap."

    result = constraints_engine.evaluate_constraints(jd, constraints)
    remote = next(r for r in result.hard_results if r.id == "remote_first_hybrid_ok")
    assert remote.status == expected_status
    assert result.presence_requires_exception is requires_exception
    if expected_status == "failed":
        assert result.decision == "no_go"
    else:
        assert result.decision != "no_go" or remote.status == "failed"


# --- Boundary: Fit-Check Outcomes ---


def test_v3_boundary_1_office_day_fit_check_ok(client: TestClient):
    jd = (
        "Remote-first. Bis zu 1 Tag pro Woche im Office. "
        "Product Manager with product ownership and roadmap."
    )
    body = client.post("/fit-check", json={"job_description": jd}).json()
    pp = body["presence_policy"]
    assert pp["level"] == "remote_first_ok"
    assert pp["outcome"] == "ok"
    assert pp["exception_granted"] is False
    assert body["status_flag"] == "proceed"
    hard = {r["id"]: r["status"] for r in body["constraint_check"]["hard_results"]}
    assert hard["remote_first_hybrid_ok"] == "passed"


def test_v3_boundary_2_days_weak_fit_exception_denied(client: TestClient):
    body = client.post(
        "/fit-check",
        json={"job_description": WEAK_PRODUCT_JD, "role_ids": ["ai_product_manager"]},
    ).json()
    pp = body["presence_policy"]
    assert pp["level"] == "two_to_three_office_days"
    assert pp["outcome"] == "exception_denied"
    assert pp["exception_granted"] is False
    assert pp["best_role_score"] is not None
    assert pp["best_role_score"] < pp["exceptional_score_threshold"]
    assert body["status_flag"] == "no_go"
    assert body["results"] == []
    assert body["excluded_roles"]
    assert body["constraint_check"]["presence_requires_exception"] is True
    hard = {r["id"]: r["status"] for r in body["constraint_check"]["hard_results"]}
    assert hard["remote_first_hybrid_ok"] == "penalty"


def test_v3_boundary_2_days_strong_fit_exception_granted(client: TestClient):
    jd = f"2 Präsenztage im Büro. {STRONG_PRODUCT_JD_BODY}"
    body = client.post(
        "/fit-check",
        json={"job_description": jd, "role_ids": ["ai_product_manager"]},
    ).json()
    pp = body["presence_policy"]
    assert pp["level"] == "two_to_three_office_days"
    assert pp["outcome"] == "exception_granted"
    assert pp["exception_granted"] is True
    assert pp["best_role_score"] >= pp["exceptional_score_threshold"]
    assert pp["exceptional_score_threshold"] == 90
    assert "Ausnahme" in pp["reason"]
    assert body["status_flag"] == "proceed"
    assert body["results"]
    assert body["results"][0]["role_id"] == "ai_product_manager"


def test_v3_boundary_3_days_strong_fit_exception_visible(client: TestClient):
    """3 Tage: Ausnahme muss begründet und sichtbar sein (kein stilles Durchwinken)."""
    jd = f"3 Präsenztage pro Woche. {STRONG_PRODUCT_JD_BODY}"
    body = client.post(
        "/fit-check",
        json={"job_description": jd, "role_ids": ["ai_product_manager"]},
    ).json()
    pp = body["presence_policy"]
    assert pp["level"] == "two_to_three_office_days"
    assert pp["outcome"] == "exception_granted"
    assert pp["exception_granted"] is True
    assert pp["best_role_score"] is not None
    assert pp["best_role_score"] >= pp["exceptional_score_threshold"]
    assert "Ausnahme" in pp["reason"]
    assert str(pp["exceptional_score_threshold"]) in pp["reason"]
    assert str(pp["best_role_score"]) in pp["reason"]
    assert body["status_flag"] == "proceed"
    assert body["constraint_check"]["presence_requires_exception"] is True


def test_v3_boundary_2_days_denied_reason_visible(client: TestClient):
    """2 Tage ohne Top-Fit: Ablehnung muss in presence_policy begründet sein."""
    body = client.post(
        "/fit-check",
        json={"job_description": WEAK_PRODUCT_JD, "role_ids": ["ai_product_manager"]},
    ).json()
    pp = body["presence_policy"]
    assert pp["outcome"] == "exception_denied"
    assert pp["exception_granted"] is False
    assert "Ausnahme" in pp["reason"]
    assert "verweigert" in pp["reason"].casefold() or "<" in pp["reason"]
    assert pp["best_role_score"] is not None
    assert str(pp["best_role_score"]) in pp["reason"]
    assert str(pp["exceptional_score_threshold"]) in pp["reason"]
    assert body["status_flag"] == "no_go"


def test_v3_boundary_gt3_days_hard_no_go(client: TestClient):
    jd = f"4 Präsenztage pro Woche. {STRONG_PRODUCT_JD_BODY}"
    body = client.post(
        "/fit-check",
        json={"job_description": jd, "role_ids": ["ai_product_manager"]},
    ).json()
    pp = body["presence_policy"]
    assert pp["level"] == "hard_presence"
    assert pp["outcome"] == "no_go"
    assert pp["exception_granted"] is False
    assert body["status_flag"] == "no_go"
    assert body["results"] == []
    assert body["excluded_roles"] == []


def test_v3_feste_praesenzpflicht_hard_no_go_even_with_strong_jd(client: TestClient):
    jd = f"Feste Präsenzpflicht. {STRONG_PRODUCT_JD_BODY}"
    body = client.post(
        "/fit-check",
        json={"job_description": jd, "role_ids": ["ai_product_manager"]},
    ).json()
    pp = body["presence_policy"]
    assert pp["level"] == "hard_presence"
    assert pp["outcome"] == "no_go"
    assert body["status_flag"] == "no_go"
    assert body["results"] == []


def test_v3_presence_policy_always_present_on_ok_path(client: TestClient):
    jd = (
        "Remote hybrid AI Product Manager with product ownership and roadmap. "
        "B2B SaaS, GovTech."
    )
    body = client.post("/fit-check", json={"job_description": jd}).json()
    assert "presence_policy" in body
    PresencePolicyResult.model_validate(body["presence_policy"])
    assert body["presence_policy"]["level"] == "remote_first_ok"
    assert body["presence_policy"]["outcome"] == "ok"


# --- Smoke: echte Grauzonen-JD (Präsenz als Trade-off) ---


def test_v3_smoke_grayzone_presence_tradeoff(client: TestClient):
    """Smoke: Präsenz nicht absolut, sondern Trade-off → Penalty + explizite Ausnahme.

    Erwartungen:
    1) Kein hartes No-Go allein wegen „Präsenzpflicht“-Negation
    2) remote_first_hybrid_ok = penalty (2 Tage)
    3) presence_policy zeigt Ausnahme explizit (granted bei starkem Fit)
    4) Scoring läuft; Ausnahme nicht stillschweigend
    """
    body = client.post(
        "/fit-check",
        json={
            "job_description": GRAYZONE_PRESENCE_TRADEOFF_JD,
            "role_ids": ["ai_product_manager"],
        },
    ).json()

    hard = {r["id"]: r["status"] for r in body["constraint_check"]["hard_results"]}
    assert hard["remote_first_hybrid_ok"] == "penalty"
    assert body["constraint_check"]["presence_requires_exception"] is True

    pp = body["presence_policy"]
    PresencePolicyResult.model_validate(pp)
    assert pp["level"] == "two_to_three_office_days"
    assert pp["outcome"] == "exception_granted"
    assert pp["exception_granted"] is True
    assert pp["best_role_score"] is not None
    assert pp["best_role_score"] >= pp["exceptional_score_threshold"]
    assert "Ausnahme" in pp["reason"]

    assert body["status_flag"] == "proceed"
    assert body["results"]
    assert body["results"][0]["role_id"] == "ai_product_manager"
    assert body["results"][0]["score"] >= 90
