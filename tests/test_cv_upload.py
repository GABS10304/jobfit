"""CV ingest + bootstrap + upload API tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.cv_bootstrap import bootstrap_from_text
from backend.cv_ingest import CvIngestError, extract_text
from backend.main import app

client = TestClient(app)

SAMPLE_CV_MD = """# Lebenslauf

## Max Mustermann
Product Manager / AI Product Manager

Erfahrung mit Product Discovery, Roadmap, Priorisierung und Stakeholder.
AI-Use-Cases validiert, Prototyping mit Python und LangChain.
B2B SaaS, GovTech, regulated environments.
Tools: Jira, SQL, Streamlit, BigQuery, MCP.
"""


def test_extract_rejects_doc():
    with pytest.raises(CvIngestError, match="Legacy .doc"):
        extract_text("cv.doc", b"fake")


def test_extract_md_text():
    text = extract_text("cv.md", SAMPLE_CV_MD.encode("utf-8"))
    assert "Product Manager" in text


def test_bootstrap_suggests_role_and_signals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import backend.profile_store as store

    monkeypatch.setattr(store, "PROFILES_DIR", tmp_path)
    result = bootstrap_from_text(
        SAMPLE_CV_MD,
        user_id="max",
        display_name="",
        source_filename="max-cv.md",
    )
    assert result.suggested_role_id == "ai_product_manager"
    assert "product_discovery" in result.matched_signal_ids
    assert result.profile.constraints.hard_constraints == []
    assert "# Master CV – Draft" in result.cv_draft_md
    assert result.profile.role_fit_profile.roles
    role = result.profile.role_fit_profile.roles[0]
    assert role.role_id == "ai_product_manager"
    assert len(role.core_signals_skills) >= 1


def test_cv_upload_api_updates_completeness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import backend.profile_store as store

    monkeypatch.setattr(store, "PROFILES_DIR", tmp_path)

    res = client.post(
        "/onboarding/cv-upload",
        data={"user_id": "max", "display_name": ""},
        files={"file": ("max-cv.md", SAMPLE_CV_MD.encode("utf-8"), "text/markdown")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["user_id"] == "max"
    assert body["completeness"]["fit_ready_pct"] < 100
    assert body["completeness"]["fit_check_unlocked"] is False
    assert any("Hard Constraint" in m for m in body["completeness"]["missing_required"])
    assert (tmp_path / "max" / "cv_draft.md").exists()
    assert (tmp_path / "max" / "profile.yaml").exists()


def test_cv_upload_rejects_gabriel():
    res = client.post(
        "/onboarding/cv-upload",
        data={"user_id": "gabriel"},
        files={"file": ("x.md", b"# x", "text/markdown")},
    )
    assert res.status_code == 400
