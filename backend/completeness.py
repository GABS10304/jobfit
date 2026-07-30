"""Profile completeness – Fit-ready % and profile-depth % (no fit scoring).

Spec: docs/USER_ONBOARDING.md
"""

from __future__ import annotations

from backend.models import (
    CompletenessBlockScore,
    CompletenessSnapshot,
    Constraints,
    RoleFitProfile,
    RoleSignals,
    UserProfile,
)

REQUIRED_HARD_IDS: tuple[str, ...] = (
    "remote_first_hybrid_ok",
    "no_hard_sales",
    "product_ownership_required",
)

WEIGHT_ROLES = 25.0
WEIGHT_HARD = 30.0
WEIGHT_SIGNALS = 35.0
WEIGHT_PREFS = 10.0
FIT_READY_WEIGHT_SUM = WEIGHT_ROLES + WEIGHT_HARD + WEIGHT_SIGNALS  # 90

MIN_SKILLS_PER_ROLE = 5
MIN_DOMAINS_PER_ROLE = 2


def _roles_block(profile: RoleFitProfile) -> tuple[float, CompletenessBlockScore, list[str]]:
    missing: list[str] = []
    valid = [
        r
        for r in profile.roles
        if (r.role_id or "").strip() and (r.role_name or "").strip()
    ]
    if not valid:
        missing.append("Mindestens eine Zielrolle (role_id + role_name)")
        score_pct = 0
        detail = "Keine gültige Zielrolle"
    else:
        score_pct = 100
        detail = f"{len(valid)} Rolle(n) bestätigt"
    weighted = WEIGHT_ROLES * (score_pct / 100.0)
    block = CompletenessBlockScore(
        id="roles",
        label="Zielrollen",
        weight=WEIGHT_ROLES,
        score_pct=score_pct,
        detail=detail,
    )
    return weighted, block, missing


def _hard_block(constraints: Constraints) -> tuple[float, CompletenessBlockScore, list[str]]:
    present = {h.id for h in constraints.hard_constraints}
    missing: list[str] = []
    per = WEIGHT_HARD / len(REQUIRED_HARD_IDS)
    earned = 0.0
    answered: list[str] = []
    for hid in REQUIRED_HARD_IDS:
        if hid in present:
            earned += per
            answered.append(hid)
        else:
            missing.append(f"Hard Constraint fehlt: {hid}")
    score_pct = int(round(100 * earned / WEIGHT_HARD)) if WEIGHT_HARD else 0
    block = CompletenessBlockScore(
        id="hard_constraints",
        label="Hard Constraints",
        weight=WEIGHT_HARD,
        score_pct=score_pct,
        detail=f"{len(answered)}/{len(REQUIRED_HARD_IDS)} gesetzt",
    )
    return earned, block, missing


def _role_signals_pct(role: RoleSignals) -> int:
    skills_ok = len(role.core_signals_skills) >= MIN_SKILLS_PER_ROLE
    domains_ok = len(role.core_signals_domains) >= MIN_DOMAINS_PER_ROLE
    if skills_ok and domains_ok:
        return 100
    # Partial credit within a role
    skill_ratio = min(1.0, len(role.core_signals_skills) / MIN_SKILLS_PER_ROLE)
    domain_ratio = min(1.0, len(role.core_signals_domains) / MIN_DOMAINS_PER_ROLE)
    return int(round(100 * (0.7 * skill_ratio + 0.3 * domain_ratio)))


def _signals_block(profile: RoleFitProfile) -> tuple[float, CompletenessBlockScore, list[str]]:
    missing: list[str] = []
    roles = [
        r
        for r in profile.roles
        if (r.role_id or "").strip() and (r.role_name or "").strip()
    ]
    if not roles:
        score_pct = 0
        detail = "Keine Rollen für Signal-Check"
        missing.append(
            f"Kernsignale: pro Rolle ≥{MIN_SKILLS_PER_ROLE} Skills und "
            f"≥{MIN_DOMAINS_PER_ROLE} Domains"
        )
    else:
        scores = [_role_signals_pct(r) for r in roles]
        score_pct = int(round(sum(scores) / len(scores)))
        weak = [
            r.role_id
            for r, s in zip(roles, scores)
            if s < 100
        ]
        detail = f"Ø {score_pct}% über {len(roles)} Rolle(n)"
        if weak:
            missing.append(
                "Kernsignale unvollständig für: "
                + ", ".join(weak)
                + f" (min. {MIN_SKILLS_PER_ROLE} Skills, {MIN_DOMAINS_PER_ROLE} Domains)"
            )
    weighted = WEIGHT_SIGNALS * (score_pct / 100.0)
    block = CompletenessBlockScore(
        id="core_signals",
        label="Kernsignale",
        weight=WEIGHT_SIGNALS,
        score_pct=score_pct,
        detail=detail,
    )
    return weighted, block, missing


def _prefs_block(constraints: Constraints) -> tuple[float, CompletenessBlockScore]:
    parts: list[bool] = []
    parts.append(bool(constraints.soft_constraints))
    loc = constraints.location_preferences
    parts.append(
        bool(
            loc
            and (
                loc.preferred_locations
                or (loc.travel_tolerance or "").strip()
            )
        )
    )
    comp = constraints.compensation
    parts.append(
        bool(
            comp
            and (
                comp.min_annual_base is not None
                or comp.target_annual_base is not None
            )
        )
    )
    jt = constraints.job_types
    parts.append(bool(jt and jt.preferred))
    filled = sum(1 for p in parts if p)
    score_pct = int(round(100 * filled / len(parts)))
    weighted = WEIGHT_PREFS * (score_pct / 100.0)
    block = CompletenessBlockScore(
        id="prefs",
        label="Prefs (optional)",
        weight=WEIGHT_PREFS,
        score_pct=score_pct,
        detail=f"{filled}/{len(parts)} Pref-Bereiche",
    )
    return weighted, block


def compute_completeness(user_profile: UserProfile) -> CompletenessSnapshot:
    """Pure function: UserProfile → CompletenessSnapshot."""
    roles_w, roles_b, miss_r = _roles_block(user_profile.role_fit_profile)
    hard_w, hard_b, miss_h = _hard_block(user_profile.constraints)
    sig_w, sig_b, miss_s = _signals_block(user_profile.role_fit_profile)
    prefs_w, prefs_b = _prefs_block(user_profile.constraints)

    fit_raw = roles_w + hard_w + sig_w
    fit_ready_pct = int(round(100 * fit_raw / FIT_READY_WEIGHT_SUM))
    profile_depth_pct = int(round(roles_w + hard_w + sig_w + prefs_w))

    missing = miss_r + miss_h + miss_s
    return CompletenessSnapshot(
        fit_ready_pct=min(100, max(0, fit_ready_pct)),
        profile_depth_pct=min(100, max(0, profile_depth_pct)),
        fit_check_unlocked=fit_ready_pct >= 100 and not missing,
        missing_required=missing,
        blocks=[roles_b, hard_b, sig_b, prefs_b],
    )
