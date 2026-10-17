"""Salary forecast: stated figure wins, otherwise an explainable band estimate."""

from __future__ import annotations

import json

import pytest

from backend.sourcing.salary_estimate import estimate_salary, load_bands
from backend.sourcing.salary_filter import extract_salary_range, passes_salary_gate


def est(title, jd="", location=None, **kw):
    return estimate_salary(title=title, jd_text=jd, location=location, **kw)


def test_stated_range_wins():
    e = est("Product Manager", "Gehalt: 70.000 - 90.000 € brutto. Berlin.", "Berlin")
    assert (e.low, e.high, e.basis, e.confidence) == (70000, 90000, "stated", "hoch")
    assert "laut Anzeige" in e.label()


def test_benefit_budget_is_not_a_salary():
    jd = "Benefits: 3.000 € Benefits-Budget pro Jahr, VSOP, Hybrid in München."
    assert extract_salary_range(jd) is None
    assert passes_salary_gate(jd, 80000)  # no false rejection on a set floor
    e = est("Senior Product Manager", jd, "München")
    assert e.basis == "estimated"


def test_plausible_figure_after_implausible_one():
    assert extract_salary_range("1.500 € Budget, Jahresgehalt 85.000 €") == (85000, 85000)


@pytest.mark.parametrize("title, level", [
    ("Junior Product Manager", "junior"),
    ("Product Manager", "mid"),
    ("Senior Product Manager", "senior"),
    ("AI Lead Product Manager", "lead"),
    ("Senior Principal Product Manager", "lead"),
    ("Head of Product", "head"),
    ("VP Product", "cpo"),
])
def test_level_from_title(title, level):
    assert est(title, location="Hamburg").level == level


def test_years_raise_level():
    assert est("Product Manager", "Du bringst 10+ Jahre Erfahrung mit.", "Hamburg").level == "lead"
    assert est("Product Manager", "mindestens 7 Jahre", "Hamburg").level == "senior"


def test_multipliers_and_factors_are_explained():
    bands = load_bands()
    base_low, base_high = bands["levels"]["DE"]["senior"]
    e = est("Senior AI Product Manager", "", "München")
    assert e.low == round(base_low * 1.10 * 1.07 / 1000) * 1000
    assert e.factors[:3] == ["Senior", "KI-/ML-Rolle", "München"]
    assert e.confidence == "mittel"


def test_generic_ai_word_in_jd_does_not_make_an_ai_role():
    e = est("Product Manager", "Requirements also for AI coding agents as users.", "Hamburg")
    assert "KI-/ML-Rolle" not in e.factors


def test_location_field_beats_hq_city_in_text():
    e = est("Product Manager", "Startup aus Berlin, du arbeitest remote.", "Remote (Germany)")
    assert "Remote DE" in e.factors and "Berlin" not in e.factors


def test_switzerland_uses_chf_bands():
    e = est("Senior Product Manager", "", "Zürich")
    assert e.currency == "CHF" and e.region == "CH" and e.low >= 150000
    assert "k CHF" in e.label()


def test_startup_flags_equity_and_discount():
    e = est("Senior Product Manager", "Seed-finanziert, VSOP für alle.", "Hamburg")
    assert e.equity_note and "+ Equity" in e.label()
    plain = est("Senior Product Manager", "", "Hamburg")
    assert e.high < plain.high


def test_below_minimum_flag():
    e = est("Junior Product Manager", "", "Berlin", min_annual_base=80000)
    assert e.below_minimum is True and "unter deinem Minimum" in e.label()
    assert est("Head of Product", "", "Berlin", min_annual_base=80000).below_minimum is False


def test_fit_payload_and_shortlist_show_salary(tmp_path):
    from scripts import build_daily_shortlist as bds
    from scripts.fetch_jobs_batch import _run_fit_check
    from backend.sourcing.personio import NormalizedJobDescription

    job = NormalizedJobDescription(
        title="Senior AI Product Manager", location="München", work_mode="Hybrid",
        employment_type=None, url="https://x.jobs.personio.de/job/123",
        jd_text="AI Product Manager, product ownership, roadmap, product discovery. Hybrid.",
        source="personio", fetched_at="2026-10-17T00:00:00+00:00",
    )
    _fit, payload = _run_fit_check(job)
    assert payload["salary"]["basis"] == "estimated" and "k€" in payload["salary_label"]

    artifact = tmp_path / "a.json"
    artifact.write_text(json.dumps({"passed": [], "watchlist": [{
        "url": job.url, "title": job.title, "sourcing_bucket": "watchlist",
        "fit_check": payload, "job": job.to_dict()}]}), encoding="utf-8")
    out = tmp_path / "s.md"
    bds.build_shortlist(artifact, run_date="20261017", out_path=out,
                        state_path=tmp_path / "st" / "jobs_state.json")
    assert "💶 Gehalt:" in out.read_text(encoding="utf-8")
