"""Tests for Personio batch discovery and filtering."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from backend.sourcing.filtering import evaluate_default_filter, passes_default_filter
from backend.sourcing.personio import (
    discover_job_urls,
    extract_job_urls_from_html,
    is_personio_board_url,
    is_personio_job_url,
    normalize_board_url,
    parse_personio_html,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
BOARD_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "personio_flex_board.html"
JOB_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "personio_flex_ai_pm.html"
FLEX_BOARD_URL = "https://flex-capital-management-gmbh.jobs.personio.de/?language=de"
FLEX_JOB_URL = "https://flex-capital-management-gmbh.jobs.personio.de/job/2689046?language=de"


@pytest.fixture
def board_fixture_html() -> str:
    return BOARD_FIXTURE.read_text(encoding="utf-8")


@pytest.fixture
def job_fixture_html() -> str:
    return JOB_FIXTURE.read_text(encoding="utf-8")


def test_is_personio_board_url():
    assert is_personio_board_url(FLEX_BOARD_URL)
    assert not is_personio_board_url(FLEX_JOB_URL)
    assert is_personio_job_url(FLEX_JOB_URL)


def test_normalize_board_url():
    assert (
        normalize_board_url("https://flex-capital-management-gmbh.jobs.personio.de/?language=de")
        == "https://flex-capital-management-gmbh.jobs.personio.de/?language=de"
    )


def test_extract_job_urls_from_board_fixture(board_fixture_html: str):
    urls = extract_job_urls_from_html(board_fixture_html, FLEX_BOARD_URL)
    assert urls == [
        "https://flex-capital-management-gmbh.jobs.personio.de/job/2689046?language=de",
        "https://flex-capital-management-gmbh.jobs.personio.de/job/2600674",
        "https://flex-capital-management-gmbh.jobs.personio.de/job/2521955?language=de",
    ]


def test_discover_job_urls_uses_httpx_html(board_fixture_html: str):
    with patch("backend.sourcing.personio.fetch_page_html", return_value=board_fixture_html):
        urls = discover_job_urls(FLEX_BOARD_URL)
    assert len(urls) == 3
    assert all("/job/" in url for url in urls)


def test_discover_job_urls_playwright_fallback(board_fixture_html: str):
    with (
        patch("backend.sourcing.personio.fetch_page_html", return_value="<html></html>"),
        patch(
            "backend.sourcing.personio._fetch_board_with_playwright",
            return_value=board_fixture_html,
        ) as playwright_fetch,
    ):
        urls = discover_job_urls(FLEX_BOARD_URL)
    playwright_fetch.assert_called_once()
    assert len(urls) == 3


def test_passes_default_filter_rejects_no_go():
    assert not passes_default_filter(
        "no_go",
        top_score=90,
        top_role_id="ai_product_manager",
        title="AI Product Manager",
    )


def test_passes_default_filter_rejects_engineer_low_score():
    """Engineer with proceed + weak score must FAIL (previous false positive)."""
    assert not passes_default_filter(
        "proceed",
        top_score=36,
        top_role_id="technical_product_manager",
        title="3C - (Java) Full Stack Engineer (w/m/d)",
    )
    ok, reason = evaluate_default_filter(
        "proceed",
        top_score=36,
        top_role_id="technical_product_manager",
        title="3C - (Java) Full Stack Engineer (w/m/d)",
    )
    assert ok is False
    assert reason is not None
    assert "title_deny_keyword" in reason or "top_score" in reason


def test_passes_default_filter_rejects_schadenpruefer_verify():
    assert not passes_default_filter(
        "verify_product_ownership",
        top_score=22,
        top_role_id="agile_transformation_consultant",
        title="3C - Schadenprüfer / KFZ-Sachverständiger (m/w/d)",
    )


def test_passes_default_filter_ai_pm_proceed_high_score():
    assert passes_default_filter(
        "proceed",
        top_score=88,
        top_role_id="ai_product_manager",
        title="AI Product Manager (m/w/d)",
    )


def test_passes_default_filter_verify_high_product_role_score():
    assert passes_default_filter(
        "verify_product_ownership",
        top_score=80,
        top_role_id="technical_product_manager",
        title="Technical Product Manager",
    )


def test_passes_default_filter_rejects_non_product_top_role():
    assert not passes_default_filter(
        "proceed",
        top_score=88,
        top_role_id="scrum_master",
        title="Scrum Master with product overlap",
    )


def test_batch_filter_pass_and_reject(job_fixture_html: str):
    from scripts.fetch_jobs_batch import _process_job

    job = parse_personio_html(
        job_fixture_html,
        FLEX_JOB_URL,
        fetched_at="2026-07-22T10:00:00+00:00",
    )

    with patch("scripts.fetch_jobs_batch.fetch_personio_job", return_value=job):
        with patch(
            "scripts.fetch_jobs_batch._run_fit_check",
            return_value={
                "status_flag": "proceed",
                "verify_product_ownership": False,
                "presence_policy": {"level": "ok", "outcome": "allowed"},
                "top_score": 88,
                "top_role_id": "ai_product_manager",
                "passes_default_filter": True,
            },
        ):
            passed = _process_job(FLEX_JOB_URL, use_playwright=False, fit_check=True)

        with patch(
            "scripts.fetch_jobs_batch._run_fit_check",
            return_value={
                "status_flag": "proceed",
                "verify_product_ownership": False,
                "presence_policy": {"level": "ok", "outcome": "allowed"},
                "top_score": 36,
                "top_role_id": "technical_product_manager",
                "passes_default_filter": False,
                "filter_reject_reason": "top_score=36<75",
            },
        ):
            rejected = _process_job(FLEX_JOB_URL, use_playwright=False, fit_check=True)

    assert passed["passes_default_filter"] is True
    assert "reject_reason" not in passed
    assert rejected["passes_default_filter"] is False
    assert rejected["reject_reason"] == "filter: top_score=36<75"
