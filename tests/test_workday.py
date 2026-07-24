"""Tests for Workday JD fetch/parser."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from backend.sourcing.personio import NormalizedJobDescription
from backend.sourcing.workday import (
    fetch_workday_job,
    is_workday_job_url,
    parse_workday_html,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_HTML = REPO_ROOT / "tests" / "fixtures" / "workday_ing_prozessmanager.html"
FIXTURE_DOM_HTML = REPO_ROOT / "tests" / "fixtures" / "workday_ing_dom_only.html"
ING_URL = (
    "https://ing.wd3.myworkdayjobs.com/de-DE/ICSGBLCOR/job/Nrnberg/"
    "Prozessmanager-Customer-Data--w-m-d-_REQ-10117364-1"
)


@pytest.fixture
def workday_fixture_html() -> str:
    return FIXTURE_HTML.read_text(encoding="utf-8")


@pytest.fixture
def workday_dom_only_html() -> str:
    return FIXTURE_DOM_HTML.read_text(encoding="utf-8")


def test_is_workday_job_url():
    assert is_workday_job_url(ING_URL)
    assert is_workday_job_url(
        "https://example.wd5.myworkdayjobs.com/en-US/Careers/job/Berlin/Role_REQ-1"
    )
    assert not is_workday_job_url(
        "https://flex-capital-management-gmbh.jobs.personio.de/job/2689046"
    )
    assert not is_workday_job_url("https://ing.wd3.myworkdayjobs.com/de-DE/ICSGBLCOR")


def test_parse_workday_html_json_ld_fixture(workday_fixture_html: str):
    job = parse_workday_html(
        workday_fixture_html,
        ING_URL,
        fetched_at="2026-07-24T10:00:00+00:00",
    )
    assert isinstance(job, NormalizedJobDescription)
    assert job.title == "Prozessmanager Customer Data (w/m/d)"
    assert job.location == "Nürnberg"
    assert job.work_mode == "Hybrid"
    assert job.employment_type is None  # JSON-LD employmentType OTHER → ignored
    assert "Kundendatenprozesse" in job.jd_text
    assert "Data Steward" in job.jd_text
    assert "Hybrides Arbeitsmodell" in job.jd_text
    assert job.source == "workday"
    assert job.url == ING_URL
    assert job.fetched_at == "2026-07-24T10:00:00+00:00"
    assert len(job.jd_text) > 500


def test_parse_workday_html_dom_og_fallback(workday_dom_only_html: str):
    job = parse_workday_html(
        workday_dom_only_html,
        ING_URL,
        fetched_at="2026-07-24T11:00:00+00:00",
    )
    assert job.title == "Prozessmanager Customer Data (w/m/d)"
    assert job.location == "Nürnberg"
    assert job.employment_type == "Full time"
    assert job.work_mode == "Hybrid"
    assert "Kundendatenprozesse" in job.jd_text
    assert job.source == "workday"


def test_fetch_workday_job_uses_http_html(workday_fixture_html: str):
    with patch(
        "backend.sourcing.workday.fetch_page_html",
        return_value=workday_fixture_html,
    ):
        job = fetch_workday_job(ING_URL)
    assert job.title.startswith("Prozessmanager")
    assert job.source == "workday"


@pytest.mark.network
def test_fetch_workday_job_live_smoke():
    try:
        job = fetch_workday_job(ING_URL)
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"network unavailable or Workday unreachable: {exc}")
    assert job.title
    assert "Prozessmanager" in job.title
    assert len(job.jd_text) > 200
    assert job.source == "workday"
    assert job.work_mode in {"Hybrid", "Remote", "On-site", None}
