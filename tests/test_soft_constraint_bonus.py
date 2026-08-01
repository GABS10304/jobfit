"""Tests for the autonomy/impact soft-constraint score bonus (2026-08-01).

Gabriel's stated motivation priority is autonomy > impact > money (money
already has its own hard gate). This bonus is a bounded nudge on top of the
existing signal-match score — never a replacement for it.
"""

from __future__ import annotations

from backend import constraints_engine, data_loader, fit_engine
from backend.fit_engine import (
    _SOFT_BONUS_CAP,
    _apply_soft_bonus,
    _soft_constraint_bonus,
)
from backend.models import ConstraintCheckResult, RoleFitResult, SoftConstraintResult

BASE_JD = (
    "AI Product Manager for B2B SaaS. Remote-first role. "
    "Product discovery, AI use case validation, stakeholder communication, "
    "requirements engineering."
)

AUTONOMY_IMPACT_JD = BASE_JD + (
    " You'll have full ownership and work in a flat hierarchy with high "
    "autonomy. This is a founding, zero to one role with high impact."
)


def _top_score(fit):
    candidates = fit.results or fit.excluded_roles
    return candidates[0].score if candidates else None


def test_autonomy_impact_cues_increase_score_within_cap():
    role_fit_profile = data_loader.load_role_fit_profile()
    constraints = data_loader.load_constraints()

    base_fit = fit_engine.run_fit_check(
        job_description=BASE_JD, profile=role_fit_profile, constraints=constraints
    )
    boosted_fit = fit_engine.run_fit_check(
        job_description=AUTONOMY_IMPACT_JD, profile=role_fit_profile, constraints=constraints
    )

    base_score = _top_score(base_fit)
    boosted_score = _top_score(boosted_fit)

    assert base_score is not None and boosted_score is not None
    assert boosted_score > base_score
    assert boosted_score - base_score <= _SOFT_BONUS_CAP


def test_constraints_engine_matches_autonomy_and_impact_cues():
    constraints = data_loader.load_constraints()
    result = constraints_engine.evaluate_constraints(AUTONOMY_IMPACT_JD, constraints)
    matched_ids = {r.id for r in result.soft_results if r.status == "matched"}
    assert "autonomy_preferred" in matched_ids
    assert "impact_preferred" in matched_ids


def _make_check(soft_results: list[SoftConstraintResult]) -> ConstraintCheckResult:
    return ConstraintCheckResult(
        decision="proceed",
        decision_reason="test",
        hard_results=[],
        soft_results=soft_results,
    )


def test_soft_constraint_bonus_sums_matched_weights():
    check = _make_check(
        [
            SoftConstraintResult(
                id="autonomy_preferred", label="x", weight=1.0, status="matched", reason="r"
            ),
        ]
    )
    assert _soft_constraint_bonus(check) == 6  # 1.0 * _SOFT_BONUS_POINTS_PER_WEIGHT(6)


def test_soft_constraint_bonus_ignores_not_matched():
    check = _make_check(
        [
            SoftConstraintResult(
                id="autonomy_preferred", label="x", weight=1.0, status="not_matched", reason="r"
            ),
        ]
    )
    assert _soft_constraint_bonus(check) == 0


def test_soft_constraint_bonus_is_capped():
    check = _make_check(
        [
            SoftConstraintResult(
                id="autonomy_preferred", label="x", weight=1.0, status="matched", reason="r"
            ),
            SoftConstraintResult(
                id="impact_preferred", label="x", weight=0.95, status="matched", reason="r"
            ),
        ]
    )
    assert _soft_constraint_bonus(check) == _SOFT_BONUS_CAP


def test_soft_constraint_bonus_ignores_legacy_topic_constraints():
    """b2b/govtech/ai-data/coaching were dormant before this change and must
    stay that way — only autonomy/impact actually move the score."""
    check = _make_check(
        [
            SoftConstraintResult(
                id="b2b_preferred", label="x", weight=0.8, status="matched", reason="r"
            ),
            SoftConstraintResult(
                id="govtech_or_regulated_preferred", label="x", weight=0.9, status="matched", reason="r"
            ),
            SoftConstraintResult(
                id="ai_or_data_preferred", label="x", weight=0.85, status="matched", reason="r"
            ),
        ]
    )
    assert _soft_constraint_bonus(check) == 0


def test_apply_soft_bonus_caps_score_at_100_and_recomputes_threshold():
    results = [
        RoleFitResult(
            role_id="ai_product_manager",
            role_name="x",
            score=97,
            matched_signals=[],
            missing_signals=[],
            passes_review_threshold=True,
        ),
        RoleFitResult(
            role_id="technical_product_manager",
            role_name="x",
            score=70,
            matched_signals=[],
            missing_signals=[],
            passes_review_threshold=False,
        ),
    ]
    boosted = _apply_soft_bonus(results, 8, min_review=75)
    assert boosted[0].score == 100  # capped, not 105
    assert boosted[1].score == 78
    assert boosted[1].passes_review_threshold is True  # crossed the 75 threshold


def test_apply_soft_bonus_noop_when_bonus_zero():
    results = [
        RoleFitResult(
            role_id="ai_product_manager",
            role_name="x",
            score=50,
            matched_signals=[],
            missing_signals=[],
            passes_review_threshold=False,
        ),
    ]
    assert _apply_soft_bonus(results, 0, min_review=75) == results
