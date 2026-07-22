"""Tests for Personio JD fetch/parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.sourcing.personio import (
    NormalizedJobDescription,
    fetch_personio_job,
    is_personio_job_url,
    parse_personio_html,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_HTML = REPO_ROOT / "tests" / "fixtures" / "personio_flex_ai_pm.html"
FLEX_URL = "https://flex-capital-management-gmbh.jobs.personio.de/job/2689046?language=de"


@pytest.fixture
def personio_fixture_html() -> str:
    return FIXTURE_HTML.read_text(encoding="utf-8")


def test_is_personio_job_url():
    assert is_personio_job_url(FLEX_URL)
    assert not is_personio_job_url("https://example.com/job/123")


def test_parse_personio_html_fixture(personio_fixture_html: str):
    job = parse_personio_html(
        personio_fixture_html,
        FLEX_URL,
        fetched_at="2026-07-22T10:00:00+00:00",
    )
    assert isinstance(job, NormalizedJobDescription)
    assert job.title == "AI Product Manager (m/w/d)"
    assert job.location == "Berlin, Berlin / Hybrid"
    assert job.work_mode == "Hybrid"
    assert "Vollzeit" in (job.employment_type or "")
    assert "Festanstellung" in (job.employment_type or "")
    assert "AI-Projekte vorantreiben" in job.jd_text
    assert "Prototypen bauen" in job.jd_text
    assert job.source == "personio"
    assert job.url == FLEX_URL
    assert job.fetched_at == "2026-07-22T10:00:00+00:00"


@pytest.mark.network
def test_fetch_personio_job_live_smoke():
    try:
        job = fetch_personio_job(FLEX_URL)
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"network unavailable or Personio unreachable: {exc}")
    assert job.title
    assert len(job.jd_text) > 200
    assert job.work_mode in {"Hybrid", "Remote", "On-site", None}
