"""Flexible presence mode (Gabriel 2026-10-17): presence never blocks, it is reported."""

from __future__ import annotations

import pytest

from backend import constraints_engine, data_loader, fit_engine
from backend.models import HardConstraint

BODY = (
    " AI Product Manager for B2B SaaS. You own product ownership and the roadmap. "
    "Product discovery, AI use case validation, stakeholder communication."
)


def _flex() -> HardConstraint:
    return HardConstraint(id="remote_first_hybrid_ok", label="presence", mode="flexible")


@pytest.mark.parametrize(
    "prefix, level",
    [
        ("Remote-first, hybrid.", "remote_first_ok"),
        ("2 Präsenztage im Büro.", "two_to_three_office_days"),
        ("Feste Präsenzpflicht, 5 Tage vor Ort.", "hard_presence"),
        ("Büro in Berlin.", "unclear"),
    ],
)
def test_flexible_never_blocks_but_reports_level(prefix, level):
    result = constraints_engine._eval_remote_first_hybrid_ok(_flex(), (prefix + BODY).casefold())
    assert result.status == "passed"
    assert result.presence_level == level


def test_repo_constraints_run_flexible():
    hard = {h.id: h for h in data_loader.load_constraints().hard_constraints}
    assert hard["remote_first_hybrid_ok"].mode == "flexible"


def test_onsite_jd_is_scored_and_level_visible():
    jd = "Feste Präsenzpflicht im Büro Berlin, vor Ort." + BODY
    fit = fit_engine.run_fit_check(
        job_description=jd,
        profile=data_loader.load_role_fit_profile(),
        constraints=data_loader.load_constraints(),
    )
    assert fit.status_flag != "no_go"
    assert fit.results or fit.excluded_roles  # roles scored, not gated away
    assert fit.presence_policy.outcome == "ok"
    assert fit.presence_policy.level == "hard_presence"


def test_strict_mode_unchanged():
    strict = HardConstraint(id="remote_first_hybrid_ok", label="presence")
    jd = ("Feste Präsenzpflicht, 5 Tage vor Ort." + BODY).casefold()
    assert constraints_engine._eval_remote_first_hybrid_ok(strict, jd).status == "failed"
