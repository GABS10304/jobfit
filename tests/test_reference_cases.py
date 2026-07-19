"""Regression against saved reference fit-check cases."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from backend import data_loader
from backend.main import app

FIXTURES = Path(__file__).resolve().parent.parent / "domain" / "fixtures"
REF_CASE = FIXTURES / "ref_senior_product_transformation_lead_hybrid.yaml"


@pytest.fixture
def client() -> TestClient:
    data_loader.clear_domain_cache()
    return TestClient(app)


def _load_case() -> dict:
    with REF_CASE.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_reference_case_senior_product_transformation_lead(client: TestClient):
    case = _load_case()
    expected = case["expected"]

    response = client.post(
        "/fit-check",
        json={"job_description": case["job_description"]},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["status_flag"] == expected["status_flag"]
    assert body["verify_product_ownership"] is expected["verify_product_ownership"]

    hard_by_id = {h["id"]: h for h in body["constraint_check"]["hard_results"]}
    for cid, status in expected["hard_constraints"].items():
        assert hard_by_id[cid]["status"] == status

    ordered = body["results"] + body["excluded_roles"]
    assert len(ordered) >= expected["min_scored_roles"]
    assert bool(ordered) is expected["scoring_runs"]

    top_ids = [r["role_id"] for r in ordered[: len(expected["top_role_ids"])]]
    assert top_ids == expected["top_role_ids"]

    id_pos = {r["role_id"]: i for i, r in enumerate(ordered)}
    for assertion in expected["ranking_assertions"]:
        assert id_pos[assertion["product_role"]] < id_pos[assertion["before_role"]]
