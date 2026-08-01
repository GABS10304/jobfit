"""Fit Engine – pipeline: constraints → role scoring → threshold filter → presence exception."""

from __future__ import annotations

import re

from backend import constraints_engine
from backend.models import (
    ConstraintCheckResult,
    Constraints,
    FitCheckResponse,
    PresencePolicyResult,
    RoleFitProfile,
    RoleFitResult,
    RoleSignals,
)
from backend.signal_lexicon import candidates_for_signal

# Lower number = higher priority when scores are similar.
# 1 = echte Produktverantwortung, 2 = produktnahe Koordination,
# 3 = Coaching / Transformation ohne klares Produktmandat.
ROLE_RANK_TIER: dict[str, int] = {
    "ai_product_manager": 1,
    "technical_product_manager": 1,
    "b2b_saas_govtech_product_lead": 1,
    "product_transformation_lead": 1,
    "agile_project_lead": 2,
    "client_solutions_lead": 2,
    "product_operations": 2,
    "scrum_master": 2,
    "agile_coach": 3,
    "agile_transformation_consultant": 3,
}

# Scores within this band are treated as "ähnlich".
# Tier-2 needs more than BAND points ahead of Tier-1 to rank higher;
# Tier-3 needs more than 2*BAND ahead of Tier-1.
# Gray-zone policy: Produkt vor Koordination vor Coaching.
SIMILAR_SCORE_BAND = 12

_UNKNOWN_TIER = 99

# Soft-constraint score bonus: a bounded nudge for JDs that signal Gabriel's
# stated motivation priorities (autonomy > impact > money — money already
# has its own hard salary gate, so it isn't a soft constraint here). Capped
# well below SIMILAR_SCORE_BAND so it can't turn a genuinely weak skill-fit
# into a false strong-pass; it only reorders among already-plausible roles
# and nudges borderline cases (e.g. 70 -> 75+) over the review threshold.
#
# Deliberately scoped to just these two ids, not "all matched soft
# constraints" — the pre-existing b2b/govtech/ai-data/coaching soft
# constraints were dormant (declared with a `weight` field but never
# affecting score) before this change, and stay that way; only the new
# autonomy/impact motivation signal actually moves the score.
_SOFT_BONUS_CONSTRAINT_IDS = frozenset({"autonomy_preferred", "impact_preferred"})
_SOFT_BONUS_POINTS_PER_WEIGHT = 6
_SOFT_BONUS_CAP = 10


def role_rank_tier(role_id: str) -> int:
    return ROLE_RANK_TIER.get(role_id, _UNKNOWN_TIER)


def rank_roles(results: list[RoleFitResult]) -> list[RoleFitResult]:
    """Sort by score, with a strong product-ownership tie-breaker.

    Cursor-Regel / Fit-check-Policy:
    Bei ähnlichen Scores gilt Produkt > Koordination > Coaching.
    Nur ein deutlicher Score-Vorsprung darf eine niedrigere Tier-Rolle nach oben ziehen.
    """

    def sort_key(r: RoleFitResult) -> tuple:
        tier = role_rank_tier(r.role_id)
        # Strong priority boost for product ownership in gray zones.
        adjusted = r.score - (tier - 1) * SIMILAR_SCORE_BAND
        return (-adjusted, tier, -r.score, r.role_id)

    return sorted(results, key=sort_key)


def _normalize(text: str) -> str:
    return text.casefold()


def _phrase_in_jd(phrase: str, jd_normalized: str) -> bool:
    """Substring match; short tokens (<=3) require rough word boundaries."""
    if not phrase:
        return False
    if len(phrase) <= 3:
        pattern = rf"(?<![a-z0-9äöüß_]){re.escape(phrase)}(?![a-z0-9äöüß_])"
        return re.search(pattern, jd_normalized) is not None
    return phrase in jd_normalized


def _signal_matches(signal: str, jd_normalized: str) -> bool:
    """Match if the signal token or a DE/EN synonym appears in the JD."""
    for candidate in candidates_for_signal(signal):
        if _phrase_in_jd(candidate, jd_normalized):
            return True
    return False


def matched_candidate(signal: str, jd_normalized: str) -> str | None:
    """Return the first matching candidate phrase (for explainability/tests)."""
    for candidate in candidates_for_signal(signal):
        if _phrase_in_jd(candidate, jd_normalized):
            return candidate
    return None


def _required_signals(role: RoleSignals) -> list[str]:
    """Skills + domains + required tools. Always in the score denominator."""
    return [
        *role.core_signals_skills,
        *role.core_signals_domains,
        *role.core_signals_tools,
    ]


def _all_signals(role: RoleSignals) -> list[str]:
    """Flat union for callers that need every signal id (required + optional)."""
    return [
        *_required_signals(role),
        *role.optional_signals_tools,
    ]


_TIER_REASON = {
    1: "echte Produktverantwortung",
    2: "produktnahe Koordination",
    3: "Coaching/Transformation ohne klares Produktmandat",
}


def _role_reason(
    role: RoleSignals,
    *,
    score: int,
    matched_required: list[str],
    missing_required: list[str],
    matched_optional: list[str],
    denominator: int,
) -> str:
    tier = role_rank_tier(role.role_id)
    tier_label = _TIER_REASON.get(tier, "sonstige Rolle")
    if denominator == 0:
        return f"Keine Kernsignale definiert ({tier_label})."
    numerator = len(matched_required) + len(matched_optional)
    req_total = len(matched_required) + len(missing_required)
    top = ", ".join((matched_required + matched_optional)[:3]) or "—"
    optional_note = (
        f", optional+{len(matched_optional)}"
        if role.optional_signals_tools
        else ""
    )
    return (
        f"{numerator}/{denominator} Signale gematcht "
        f"(Score {score}; required {len(matched_required)}/{req_total}"
        f"{optional_note}). "
        f"Rank-Tier: {tier_label}. Top-Matches: {top}."
    )


def score_role(
    job_description: str,
    role: RoleSignals,
    *,
    min_score_for_review: int,
) -> RoleFitResult:
    """Score role against JD.

    Required signals (skills ∪ domains ∪ core_signals_tools) always enter the
    denominator. Optional tools (optional_signals_tools) use A′ semantics:
    matched → count in numerator and denominator (bonus); unmatched → ignored
    in the denominator so absent stack names do not inflate the score gap.
    Profiles without optional_signals_tools stay bit-identical to V3.
    """
    jd = _normalize(job_description)
    required = _required_signals(role)
    optional = list(role.optional_signals_tools)

    matched_required: list[str] = []
    missing_required: list[str] = []
    for signal in required:
        if _signal_matches(signal, jd):
            matched_required.append(signal)
        else:
            missing_required.append(signal)

    matched_optional: list[str] = []
    missing_optional: list[str] = []
    for signal in optional:
        if _signal_matches(signal, jd):
            matched_optional.append(signal)
        else:
            missing_optional.append(signal)

    # A′: den = required + matched optional only
    numerator = len(matched_required) + len(matched_optional)
    denominator = len(required) + len(matched_optional)
    score = 0 if denominator == 0 else round(100 * numerator / denominator)

    return RoleFitResult(
        role_id=role.role_id,
        role_name=role.role_name,
        score=score,
        matched_signals=matched_required + matched_optional,
        missing_signals=missing_required,
        matched_optional_signals=matched_optional,
        missing_optional_signals=missing_optional,
        reason=_role_reason(
            role,
            score=score,
            matched_required=matched_required,
            missing_required=missing_required,
            matched_optional=matched_optional,
            denominator=denominator,
        ),
        passes_review_threshold=score >= min_score_for_review,
    )


def score_roles(
    job_description: str,
    profile: RoleFitProfile,
    *,
    role_ids: list[str] | None = None,
    min_score_for_review: int = 75,
) -> list[RoleFitResult]:
    roles = profile.roles
    if role_ids:
        wanted = set(role_ids)
        roles = [r for r in roles if r.role_id in wanted]

    results = [
        score_role(
            job_description,
            role,
            min_score_for_review=min_score_for_review,
        )
        for role in roles
    ]
    return rank_roles(results)


def snippet(job_description: str, max_len: int = 200) -> str:
    text = " ".join(job_description.split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def build_presence_policy(
    constraint_check: ConstraintCheckResult,
    *,
    exceptional_score_threshold: int,
    best_role_score: int | None = None,
) -> PresencePolicyResult:
    """V3: Präsenz immer explizit – nie stillschweigende Ausnahme."""
    remote = next(
        (r for r in constraint_check.hard_results if r.id == "remote_first_hybrid_ok"),
        None,
    )
    cues = remote.matched_cues if remote else []

    if remote is None or remote.status == "skipped":
        return PresencePolicyResult(
            level="remote_first_ok",
            outcome="ok",
            reason="remote_first_hybrid_ok nicht bewertet oder deaktiviert.",
            exceptional_score_threshold=exceptional_score_threshold,
            matched_cues=cues,
        )

    if remote.status == "failed":
        return PresencePolicyResult(
            level="hard_presence",
            outcome="no_go",
            reason=remote.reason,
            exceptional_score_threshold=exceptional_score_threshold,
            exception_granted=False,
            matched_cues=cues,
        )

    if remote.status == "unclear":
        return PresencePolicyResult(
            level="unclear",
            outcome="no_go",
            reason=remote.reason,
            exceptional_score_threshold=exceptional_score_threshold,
            exception_granted=False,
            matched_cues=cues,
        )

    if remote.status == "passed":
        return PresencePolicyResult(
            level="remote_first_ok",
            outcome="ok",
            reason=remote.reason,
            exceptional_score_threshold=exceptional_score_threshold,
            exception_granted=False,
            matched_cues=cues,
        )

    # penalty (2–3 Office-Tage)
    if best_role_score is None:
        return PresencePolicyResult(
            level="two_to_three_office_days",
            outcome="penalty_pending",
            reason=remote.reason,
            exceptional_score_threshold=exceptional_score_threshold,
            exception_granted=False,
            matched_cues=cues,
        )

    if best_role_score >= exceptional_score_threshold:
        return PresencePolicyResult(
            level="two_to_three_office_days",
            outcome="exception_granted",
            reason=(
                f"Präsenz-Ausnahme gewährt: beste Rolle Score {best_role_score} "
                f"≥ Schwelle {exceptional_score_threshold} "
                f"(min_score_for_auto_apply). Gesamtnutzen überwiegt 2–3 Office-Tage."
            ),
            exceptional_score_threshold=exceptional_score_threshold,
            best_role_score=best_role_score,
            exception_granted=True,
            matched_cues=cues,
        )

    return PresencePolicyResult(
        level="two_to_three_office_days",
        outcome="exception_denied",
        reason=(
            f"Präsenz-Ausnahme verweigert: beste Rolle Score {best_role_score} "
            f"< Schwelle {exceptional_score_threshold} "
            f"(min_score_for_auto_apply). 2–3 Office-Tage ohne außergewöhnlich starken Fit."
        ),
        exceptional_score_threshold=exceptional_score_threshold,
        best_role_score=best_role_score,
        exception_granted=False,
        matched_cues=cues,
    )


def _soft_constraint_bonus(constraint_check: ConstraintCheckResult) -> int:
    """Bounded score bonus from matched autonomy/impact constraints only."""
    total = 0.0
    for result in constraint_check.soft_results:
        if result.id in _SOFT_BONUS_CONSTRAINT_IDS and result.status == "matched":
            total += result.weight * _SOFT_BONUS_POINTS_PER_WEIGHT
    return min(round(total), _SOFT_BONUS_CAP)


def _apply_soft_bonus(results: list[RoleFitResult], bonus: int, *, min_review: int) -> list[RoleFitResult]:
    if not bonus:
        return results
    return [
        r.model_copy(
            update={
                "score": min(100, r.score + bonus),
                "passes_review_threshold": (r.score + bonus) >= min_review,
            }
        )
        for r in results
    ]


def run_fit_check(
    job_description: str,
    profile: RoleFitProfile,
    constraints: Constraints,
    role_ids: list[str] | None = None,
) -> FitCheckResponse:
    """Pipeline: constraints → flag → score → rank → presence exception → response."""
    constraint_check: ConstraintCheckResult = constraints_engine.evaluate_constraints(
        job_description, constraints
    )
    min_review = constraints.application_rules.min_score_for_review
    exceptional_threshold = constraints.application_rules.min_score_for_auto_apply
    status_flag = constraint_check.decision
    verify_flag = constraint_check.verify_product_ownership

    # Score on proceed and verify_product_ownership; only no_go skips scoring.
    if status_flag == "no_go":
        return FitCheckResponse(
            job_description_snippet=snippet(job_description),
            status_flag=status_flag,
            verify_product_ownership=verify_flag,
            presence_policy=build_presence_policy(
                constraint_check,
                exceptional_score_threshold=exceptional_threshold,
            ),
            constraint_check=constraint_check,
            results=[],
            excluded_roles=[],
        )

    scored = score_roles(
        job_description,
        profile,
        role_ids=role_ids,
        min_score_for_review=min_review,
    )
    soft_bonus = _soft_constraint_bonus(constraint_check)
    scored = _apply_soft_bonus(scored, soft_bonus, min_review=min_review)
    matching = rank_roles([r for r in scored if r.passes_review_threshold])
    excluded = rank_roles([r for r in scored if not r.passes_review_threshold])
    best_score = max((r.score for r in scored), default=0)

    presence_policy = build_presence_policy(
        constraint_check,
        exceptional_score_threshold=exceptional_threshold,
        best_role_score=(
            best_score if constraint_check.presence_requires_exception else None
        ),
    )

    # V3: 2–3 Office-Tage ohne außergewöhnlich starken Fit → no_go (explizit).
    if presence_policy.outcome == "exception_denied":
        return FitCheckResponse(
            job_description_snippet=snippet(job_description),
            status_flag="no_go",
            verify_product_ownership=verify_flag,
            presence_policy=presence_policy,
            constraint_check=constraint_check,
            results=[],
            # Scores bleiben in excluded_roles sichtbar (Explainability).
            excluded_roles=rank_roles(scored),
        )

    return FitCheckResponse(
        job_description_snippet=snippet(job_description),
        status_flag=status_flag,
        verify_product_ownership=verify_flag,
        presence_policy=presence_policy,
        constraint_check=constraint_check,
        results=matching,
        excluded_roles=excluded,
    )


# Backwards-compatible alias used by unit tests for pure scoring.
def fit_check(
    job_description: str,
    profile: RoleFitProfile,
    role_ids: list[str] | None = None,
    min_score_for_review: int = 0,
) -> list[RoleFitResult]:
    return score_roles(
        job_description,
        profile,
        role_ids=role_ids,
        min_score_for_review=min_score_for_review,
    )
