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


def _all_signals(role: RoleSignals) -> list[str]:
    return [
        *role.core_signals_skills,
        *role.core_signals_domains,
        *role.core_signals_tools,
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
    matched: list[str],
    missing: list[str],
    total: int,
) -> str:
    tier = role_rank_tier(role.role_id)
    tier_label = _TIER_REASON.get(tier, "sonstige Rolle")
    if total == 0:
        return f"Keine Kernsignale definiert ({tier_label})."
    top = ", ".join(matched[:3]) if matched else "—"
    return (
        f"{len(matched)}/{total} Signale gematcht (Score {score}). "
        f"Rank-Tier: {tier_label}. Top-Matches: {top}."
    )


def score_role(
    job_description: str,
    role: RoleSignals,
    *,
    min_score_for_review: int,
) -> RoleFitResult:
    jd = _normalize(job_description)
    signals = _all_signals(role)

    matched: list[str] = []
    missing: list[str] = []
    for signal in signals:
        if _signal_matches(signal, jd):
            matched.append(signal)
        else:
            missing.append(signal)

    total = len(signals)
    score = 0 if total == 0 else round(100 * len(matched) / total)

    return RoleFitResult(
        role_id=role.role_id,
        role_name=role.role_name,
        score=score,
        matched_signals=matched,
        missing_signals=missing,
        reason=_role_reason(
            role, score=score, matched=matched, missing=missing, total=total
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
