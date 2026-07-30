"""Tests for multi-user profile store + API (no fit-engine changes)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models import Constraints, HardConstraint, RoleFitProfile, RoleSignals, UserProfile
from backend.profile_store import create_user_profile, load_user_profile, save_user_profile
from backend.models import CreateProfileRequest

client = TestClient(app)


def test_gabriel_completeness_endpoint():
    res = client.get("/profiles/gabriel/completeness")
    assert res.status_code == 200
    body = res.json()
    assert body["user_id"] == "gabriel"
    assert body["completeness"]["fit_ready_pct"] == 100
    assert body["completeness"]["fit_check_unlocked"] is True


def test_create_and_put_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import backend.profile_store as store

    monkeypatch.setattr(store, "PROFILES_DIR", tmp_path)

    created = create_user_profile(CreateProfileRequest(user_id="ada", display_name="Ada"))
    assert created.user_id == "ada"
    assert (tmp_path / "ada" / "profile.yaml").exists()

    skills = [f"s{i}" for i in range(5)]
    domains = ["d1", "d2"]
    updated = UserProfile(
        user_id="ada",
        display_name="Ada Lovelace",
        role_fit_profile=RoleFitProfile(
            version="0.1",
            roles=[
                RoleSignals(
                    role_id="ai_product_manager",
                    role_name="AI PM",
                    core_signals_skills=skills,
                    core_signals_domains=domains,
                )
            ],
        ),
        constraints=Constraints(
            hard_constraints=[
                HardConstraint(id="remote_first_hybrid_ok", label="R", enabled=True),
                HardConstraint(id="no_hard_sales", label="S", enabled=True),
                HardConstraint(id="product_ownership_required", label="O", enabled=True),
            ]
        ),
    )
    save_user_profile(updated)
    loaded = load_user_profile("ada")
    assert loaded.display_name == "Ada Lovelace"
    assert len(loaded.role_fit_profile.roles) == 1


def test_api_create_profile_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import backend.profile_store as store

    monkeypatch.setattr(store, "PROFILES_DIR", tmp_path)

    res = client.post("/profiles", json={"user_id": "bob", "display_name": "Bob"})
    assert res.status_code == 201
    res2 = client.get("/profiles/bob/completeness")
    assert res2.status_code == 200
    assert res2.json()["completeness"]["fit_ready_pct"] == 0


def test_cannot_put_gabriel():
    res = client.put(
        "/profiles/gabriel",
        json={
            "user_id": "gabriel",
            "display_name": "Nope",
            "role_fit_profile": {"version": "0.1", "roles": []},
            "constraints": {},
        },
    )
    assert res.status_code == 400


def test_onboarding_page_served():
    res = client.get("/onboarding")
    assert res.status_code == 200
    assert "Fit-ready" in res.text
