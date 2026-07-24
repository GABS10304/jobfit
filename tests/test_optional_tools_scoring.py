"""Option A′: optional tool signals — bonus when matched, out of denominator when not."""

from __future__ import annotations

from backend import data_loader, fit_engine
from backend.models import RoleFitProfile, RoleSignals


def _profile(
    *,
    skills: list[str],
    domains: list[str] | None = None,
    tools: list[str] | None = None,
    optional_tools: list[str] | None = None,
) -> RoleFitProfile:
    return RoleFitProfile(
        roles=[
            RoleSignals(
                role_id="demo_role",
                role_name="Demo",
                core_signals_skills=skills,
                core_signals_domains=domains or [],
                core_signals_tools=tools or [],
                optional_signals_tools=optional_tools or [],
            )
        ]
    )


def test_legacy_profile_without_optional_is_bit_identical():
    """Profiles without optional_signals_tools keep V3 flat matched/total scoring."""
    profile = _profile(
        skills=["product_discovery", "mvp_validation"],
        domains=["b2b_saas"],
        tools=["python", "sql"],
    )
    jd = "Product discovery and MVP validation for B2B SaaS. Python required."
    result = fit_engine.fit_check(jd, profile)[0]
    # matched: discovery, mvp, b2b_saas, python = 4; total required 4; sql missing
    assert result.score == round(100 * 4 / 5)
    assert set(result.matched_signals) == {
        "product_discovery",
        "mvp_validation",
        "b2b_saas",
        "python",
    }
    assert result.missing_signals == ["sql"]
    assert result.matched_optional_signals == []
    assert result.missing_optional_signals == []


def test_unmatched_optional_tools_do_not_inflate_denominator():
    profile = _profile(
        skills=["product_discovery", "mvp_validation"],
        domains=["b2b_saas"],
        optional_tools=["streamlit", "ollama", "mcp"],
    )
    jd = "Product discovery and MVP validation in a B2B SaaS context."
    result = fit_engine.fit_check(jd, profile)[0]
    # Required 3/3; optional all unmatched → den = 3, not 6
    assert result.score == 100
    assert set(result.matched_signals) == {
        "product_discovery",
        "mvp_validation",
        "b2b_saas",
    }
    assert result.missing_signals == []
    assert result.matched_optional_signals == []
    assert set(result.missing_optional_signals) == {"streamlit", "ollama", "mcp"}


def test_matched_optional_tools_count_as_bonus_in_num_and_den():
    profile = _profile(
        skills=["product_discovery", "mvp_validation"],
        domains=["b2b_saas", "govtech"],
        optional_tools=["python", "streamlit", "ollama"],
    )
    # 2/4 required; 1 optional matched → A′ = 3/5 = 60
    # Required-only would be 2/4 = 50; matched optional must not lower score
    jd = "Product discovery for B2B SaaS. Strong Python skills."
    result = fit_engine.fit_check(jd, profile)[0]
    assert result.score == round(100 * 3 / 5)
    assert "python" in result.matched_signals
    assert result.matched_optional_signals == ["python"]
    assert set(result.missing_optional_signals) == {"streamlit", "ollama"}
    assert set(result.missing_signals) == {"mvp_validation", "govtech"}


def test_matched_optional_never_lowers_score_vs_required_only():
    profile = _profile(
        skills=["a", "b", "c", "d"],
        optional_tools=["python"],
    )
    jd_required_only = "a and b skills"
    required_only_score = fit_engine.fit_check(jd_required_only, profile)[0].score
    jd_with_tool = "a and b skills with python"
    with_tool_score = fit_engine.fit_check(jd_with_tool, profile)[0].score
    assert required_only_score == round(100 * 2 / 4)
    assert with_tool_score == round(100 * 3 / 5)
    assert with_tool_score >= required_only_score


def test_ai_pm_profile_loads_optional_tools():
    data_loader.clear_domain_cache()
    profile = data_loader.load_role_fit_profile()
    ai_pm = next(r for r in profile.roles if r.role_id == "ai_product_manager")
    tpm = next(r for r in profile.roles if r.role_id == "technical_product_manager")
    assert ai_pm.core_signals_tools == []
    assert len(ai_pm.optional_signals_tools) == 10
    assert tpm.core_signals_tools == []
    assert len(tpm.optional_signals_tools) == 9
    # Other roles keep required tools (V3 bit-identical path)
    coach = next(r for r in profile.roles if r.role_id == "agile_coach")
    assert coach.optional_signals_tools == []
    assert "jira" in coach.core_signals_tools
