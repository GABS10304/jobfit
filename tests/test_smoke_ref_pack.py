"""Smoke-Referenzpaket V3 – Stabilitätscheck, keine Logikänderung.

Vier Referenz-JDs: Produkt-Grauzone, starker Produktfit + 2 Office-Tage,
Koordination mit Produktanteil, Coaching/Transformation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from backend import data_loader
from backend.fit_engine import ROLE_RANK_TIER, SIMILAR_SCORE_BAND, role_rank_tier
from backend.main import app
from tests._strict_presence import strict_presence  # noqa: F401  (autouse: V3 strict policy)

FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "domain"
    / "fixtures"
    / "ref_smoke_pack_v3.yaml"
)


@pytest.fixture
def client() -> TestClient:
    data_loader.clear_domain_cache()
    return TestClient(app)


@pytest.fixture(scope="module")
def pack() -> dict:
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def _ordered(body: dict) -> list[dict]:
    return body["results"] + body["excluded_roles"]


def _assert_ranking_product_before_coord_when_similar(ordered: list[dict]) -> None:
    """Koordination darf Produkt nicht verdrängen, wenn Gap ≤ Band."""
    for i, lower in enumerate(ordered):
        for higher in ordered[:i]:
            if role_rank_tier(lower["role_id"]) == 1 and role_rank_tier(higher["role_id"]) == 2:
                gap = higher["score"] - lower["score"]
                assert gap > SIMILAR_SCORE_BAND, (
                    f"{higher['role_id']} ({higher['score']}) vor "
                    f"{lower['role_id']} ({lower['score']}) bei Gap {gap} ≤ {SIMILAR_SCORE_BAND}"
                )


def _assert_ranking_respects_band(ordered: list[dict]) -> None:
    """Coaching nur über Produkt, wenn Gap > 2× Band (klare Ausnahme)."""
    for i, lower in enumerate(ordered):
        for higher in ordered[:i]:
            lt = role_rank_tier(lower["role_id"])
            ht = role_rank_tier(higher["role_id"])
            if lt == 1 and ht == 3:
                gap = higher["score"] - lower["score"]
                assert gap > 2 * SIMILAR_SCORE_BAND, (
                    f"{higher['role_id']} ({higher['score']}) vor "
                    f"{lower['role_id']} ({lower['score']}) bei Gap {gap} ≤ {2 * SIMILAR_SCORE_BAND}"
                )


@pytest.mark.parametrize("case_index", [0, 1, 2, 3])
def test_smoke_ref_pack_case(client: TestClient, pack: dict, case_index: int):
    case = pack["cases"][case_index]
    exp = case["expected"]
    body = client.post(
        "/fit-check", json={"job_description": case["job_description"]}
    ).json()

    if "status_flag" in exp:
        assert body["status_flag"] == exp["status_flag"]
    if "status_flag_in" in exp:
        assert body["status_flag"] in exp["status_flag_in"]

    if "verify_product_ownership" in exp:
        assert body["verify_product_ownership"] is exp["verify_product_ownership"]

    pp = body["presence_policy"]
    assert pp["level"] == exp["presence_level"]
    assert pp["outcome"] == exp["presence_outcome"]
    if "exception_granted" in exp:
        assert pp["exception_granted"] is exp["exception_granted"]
    if "presence_reason_contains" in exp:
        assert exp["presence_reason_contains"] in pp["reason"]

    hard = {r["id"]: r["status"] for r in body["constraint_check"]["hard_results"]}
    if "remote_first_hybrid_ok" in exp:
        assert hard["remote_first_hybrid_ok"] == exp["remote_first_hybrid_ok"]
    if "product_ownership_required" in exp:
        assert hard["product_ownership_required"] == exp["product_ownership_required"]

    ordered = _ordered(body)
    if exp.get("scoring_runs"):
        assert ordered, f"{case['id']}: Scoring muss laufen"

    if exp.get("min_product_roles_in_top4"):
        product_ids = {rid for rid, t in ROLE_RANK_TIER.items() if t == 1}
        top4 = {r["role_id"] for r in ordered[:4]}
        assert len(top4 & product_ids) >= exp["min_product_roles_in_top4"]

    if exp.get("ranking_product_before_coord_when_similar"):
        _assert_ranking_product_before_coord_when_similar(ordered)

    if exp.get("ranking_respects_band"):
        _assert_ranking_respects_band(ordered)


def test_smoke_ref_pack_presence_never_silent_on_jd2(client: TestClient, pack: dict):
    """JD2: Ausnahme muss in presence_policy sichtbar sein (nie still)."""
    case = next(c for c in pack["cases"] if c["id"].startswith("jd2_"))
    body = client.post(
        "/fit-check", json={"job_description": case["job_description"]}
    ).json()
    pp = body["presence_policy"]
    assert pp["level"] == "two_to_three_office_days"
    assert pp["outcome"] in {"exception_granted", "exception_denied"}
    assert "Ausnahme" in pp["reason"]
    assert pp["exceptional_score_threshold"] is not None
