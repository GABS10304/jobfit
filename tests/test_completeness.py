"""Tests for profile completeness (USER_ONBOARDING.md)."""

from __future__ import annotations

from backend.completeness import (
    MIN_DOMAINS_PER_ROLE,
    MIN_SKILLS_PER_ROLE,
    compute_completeness,
)
from backend.models import (
    Constraints,
    HardConstraint,
    RoleFitProfile,
    RoleSignals,
    UserProfile,
)
from backend.profile_store import load_gabriel_profile


def _hard_all() -> list[HardConstraint]:
    return [
        HardConstraint(id="remote_first_hybrid_ok", label="Remote", enabled=True),
        HardConstraint(id="no_hard_sales", label="Sales", enabled=True),
        HardConstraint(id="product_ownership_required", label="Ownership", enabled=True),
    ]


def test_empty_profile_zero_fit_ready():
    profile = UserProfile(user_id="demo")
    snap = compute_completeness(profile)
    assert snap.fit_ready_pct == 0
    assert snap.fit_check_unlocked is False
    assert snap.missing_required


def test_roles_and_hard_without_signals_not_unlocked():
    profile = UserProfile(
        user_id="demo",
        role_fit_profile=RoleFitProfile(
            version="0.1",
            roles=[
                RoleSignals(
                    role_id="product_manager",
                    role_name="Product Manager",
                    core_signals_skills=["a"],
                    core_signals_domains=["b"],
                )
            ],
        ),
        constraints=Constraints(hard_constraints=_hard_all()),
    )
    snap = compute_completeness(profile)
    assert snap.fit_ready_pct < 100
    assert snap.fit_check_unlocked is False
    assert any("Kernsignale" in m for m in snap.missing_required)


def test_minimum_signals_unlocks_fit_ready():
    skills = [f"skill_{i}" for i in range(MIN_SKILLS_PER_ROLE)]
    domains = [f"domain_{i}" for i in range(MIN_DOMAINS_PER_ROLE)]
    profile = UserProfile(
        user_id="demo",
        role_fit_profile=RoleFitProfile(
            version="0.1",
            roles=[
                RoleSignals(
                    role_id="product_manager",
                    role_name="Product Manager",
                    core_signals_skills=skills,
                    core_signals_domains=domains,
                )
            ],
        ),
        constraints=Constraints(hard_constraints=_hard_all()),
    )
    snap = compute_completeness(profile)
    assert snap.fit_ready_pct == 100
    assert snap.fit_check_unlocked is True
    assert snap.missing_required == []


def test_gabriel_domain_is_fit_ready():
    profile = load_gabriel_profile()
    snap = compute_completeness(profile)
    assert snap.fit_ready_pct == 100
    assert snap.fit_check_unlocked is True
    # Compensation still open → depth below 100
    assert snap.profile_depth_pct < 100
    prefs = next(b for b in snap.blocks if b.id == "prefs")
    assert prefs.score_pct == 75
