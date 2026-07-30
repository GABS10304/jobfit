"""Fit-check with user_id profile resolution."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models import (
    ApplicationRules,
    Constraints,
    HardConstraint,
    RoleFitProfile,
    RoleSignals,
    UserProfile,
)

client = TestClient(app)

GOOD_JD = (
    "Remote / hybrid role: AI Product Manager for B2B SaaS in GovTech "
    "and regulated environments. You own product ownership and the roadmap. "
    "Focus: product discovery, AI use case validation, MVP validation, "
    "data driven decision making, stakeholder communication, product analytics, "
    "requirements engineering, experimental validation, privacy by design. "
    "Stack: SQL, Python, pandas, Streamlit, LangChain, Ollama, BigQuery, MCP."
)


def _hard_all() -> list[HardConstraint]:
    return [
        HardConstraint(id="remote_first_hybrid_ok", label="Remote", enabled=True),
        HardConstraint(id="no_hard_sales", label="Sales", enabled=True),
        HardConstraint(id="product_ownership_required", label="Ownership", enabled=True),
    ]


def _fit_ready_profile(user_id: str = "max") -> UserProfile:
    return UserProfile(
        user_id=user_id,
        display_name="Max",
        role_fit_profile=RoleFitProfile(
            version="0.1",
            roles=[
                RoleSignals(
                    role_id="ai_product_manager",
                    role_name="AI Product Manager",
                    core_signals_skills=[
                        "product_discovery",
                        "ai_use_case_validation",
                        "mvp_validation",
                        "data_driven_decision_making",
                        "stakeholder_communication",
                    ],
                    core_signals_domains=["b2b_saas", "govtech"],
                    core_signals_tools=["sql", "python"],
                )
            ],
        ),
        constraints=Constraints(
            hard_constraints=_hard_all(),
            application_rules=ApplicationRules(),
        ),
    )


def test_fit_check_without_user_id_unchanged():
    res = client.post("/fit-check", json={"job_description": GOOD_JD})
    assert res.status_code == 200
    body = res.json()
    assert body["status_flag"] in {"proceed", "verify_product_ownership", "no_go"}


def test_fit_check_gabriel_explicit_user_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    res = client.post(
        "/fit-check",
        json={"job_description": GOOD_JD, "user_id": "gabriel"},
    )
    assert res.status_code == 200


def test_fit_check_unknown_user_404():
    res = client.post(
        "/fit-check",
        json={"job_description": GOOD_JD, "user_id": "nobody"},
    )
    assert res.status_code == 404


def test_fit_check_not_ready_returns_403(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import backend.profile_store as store

    monkeypatch.setattr(store, "PROFILES_DIR", tmp_path)
    incomplete = UserProfile(
        user_id="max",
        role_fit_profile=RoleFitProfile(
            version="0.1",
            roles=[RoleSignals(role_id="ai_product_manager", role_name="AI PM", core_signals_skills=["a"])],
        ),
        constraints=Constraints(),
    )
    store.save_user_profile(incomplete)

    res = client.post(
        "/fit-check",
        json={"job_description": GOOD_JD, "user_id": "max"},
    )
    assert res.status_code == 403
    detail = res.json()["detail"]
    assert detail["fit_ready_pct"] < 100
    assert detail["missing_required"]


def test_fit_check_ready_user_uses_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import backend.profile_store as store

    monkeypatch.setattr(store, "PROFILES_DIR", tmp_path)
    store.save_user_profile(_fit_ready_profile("max"))

    res = client.post(
        "/fit-check",
        json={"job_description": GOOD_JD, "user_id": "max"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status_flag"] in {"proceed", "verify_product_ownership", "no_go"}
    roles_seen = [r["role_id"] for r in body["results"] + body.get("excluded_roles", [])]
    assert "ai_product_manager" in roles_seen
