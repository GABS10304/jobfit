"""Tests for Personio batch discovery, title prefilter, and filtering."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.sourcing.filtering import (
    evaluate_default_filter,
    evaluate_title_prefilter,
    evaluate_watchlist,
    passes_default_filter,
)
from backend.sourcing.personio import (
    discover_job_listings,
    discover_job_urls,
    extract_job_listings_from_html,
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


def test_extract_job_listings_with_titles(board_fixture_html: str):
    listings = extract_job_listings_from_html(board_fixture_html, FLEX_BOARD_URL)
    by_url = {item.url: item.title for item in listings}
    assert (
        by_url[
            "https://flex-capital-management-gmbh.jobs.personio.de/job/2689046?language=de"
        ]
        == "AI Product Manager (m/w/d)"
    )
    assert (
        by_url["https://flex-capital-management-gmbh.jobs.personio.de/job/2373192"]
        == "3C - (Java) Full Stack Engineer (w/m/d)"
    )
    assert (
        by_url["https://flex-capital-management-gmbh.jobs.personio.de/job/2601001"]
        == "Omikron - Product Manager Electronic Banking (m/w/d)"
    )
    # JSON-only id without anchor title
    assert by_url["https://flex-capital-management-gmbh.jobs.personio.de/job/9990001"] is None
    # Duplicate AI PM anchor collapsed to one listing
    ai_pm = [
        item
        for item in listings
        if item.url.endswith("/job/2689046?language=de")
    ]
    assert len(ai_pm) == 1


def test_extract_job_urls_from_board_fixture(board_fixture_html: str):
    urls = extract_job_urls_from_html(board_fixture_html, FLEX_BOARD_URL)
    assert urls[0].endswith("/job/2373192")
    assert any(url.endswith("/job/2689046?language=de") for url in urls)
    assert any(url.endswith("/job/9990001") for url in urls)


def test_discover_job_urls_uses_httpx_html(board_fixture_html: str):
    with patch("backend.sourcing.personio.fetch_page_html", return_value=board_fixture_html):
        urls = discover_job_urls(FLEX_BOARD_URL)
    assert len(urls) >= 7
    assert all("/job/" in url for url in urls)


def test_discover_job_listings_uses_httpx_html(board_fixture_html: str):
    with patch("backend.sourcing.personio.fetch_page_html", return_value=board_fixture_html):
        listings = discover_job_listings(FLEX_BOARD_URL)
    assert any(item.title and "AI Product Manager" in item.title for item in listings)


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
    assert len(urls) >= 7


def test_title_prefilter_allows_ai_pm():
    ok, reason = evaluate_title_prefilter("AI Product Manager (m/w/d)")
    assert ok is True
    assert reason is None


def test_title_prefilter_allows_product_manager():
    ok, reason = evaluate_title_prefilter(
        "Omikron - Product Manager Electronic Banking (m/w/d)"
    )
    assert ok is True
    assert reason is None


def test_title_prefilter_denies_engineer():
    ok, reason = evaluate_title_prefilter("3C - (Java) Full Stack Engineer (w/m/d)")
    assert ok is False
    assert reason is not None
    assert reason.startswith("title_prefilter:deny=")


def test_title_prefilter_denies_schaden():
    ok, reason = evaluate_title_prefilter(
        "3C - Schadenprüfer / KFZ-Sachverständiger (m/w/d)"
    )
    assert ok is False
    assert reason is not None
    assert "title_prefilter" in reason


def test_title_prefilter_rejects_investment_manager():
    ok, reason = evaluate_title_prefilter("(Senior) Investment Manager (m/w/d)")
    assert ok is False
    assert reason == "title_prefilter:no_allow_or_product_keyword"


def test_title_prefilter_product_keyword_without_allow_phrase():
    ok, reason = evaluate_title_prefilter("Head of Product Strategy")
    assert ok is True
    assert reason is None


def test_title_prefilter_deny_beats_product_keyword():
    ok, reason = evaluate_title_prefilter("Product Engineer (m/w/d)")
    assert ok is False
    assert reason is not None
    assert "deny=" in reason


def test_title_prefilter_denies_product_marketing():
    ok, reason = evaluate_title_prefilter("Senior Product Marketing Manager")
    assert ok is False
    assert reason is not None
    assert "deny=" in reason
    assert "marketing" in reason.casefold()


def test_title_prefilter_denies_technical_product_marketing():
    ok, reason = evaluate_title_prefilter(
        "Technical Product Marketing Manager, Piper AI SDR Agent"
    )
    assert ok is False
    assert reason is not None
    assert "deny=" in reason


def test_title_prefilter_still_allows_senior_product_manager():
    ok, reason = evaluate_title_prefilter("Senior Product Manager (m/w/d)")
    assert ok is True
    assert reason is None


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


def test_watchlist_accepts_weak_product_proceed():
    ok, reason = evaluate_watchlist(
        "proceed",
        top_score=32,
        top_role_id="technical_product_manager",
        title="AI Product Manager (m/w/d)",
    )
    assert ok is True
    assert reason == "weak_score=32<75"
    # Strong pass still fails — watchlist is not a pass
    assert not passes_default_filter(
        "proceed",
        top_score=32,
        top_role_id="technical_product_manager",
        title="AI Product Manager (m/w/d)",
    )


def test_watchlist_rejects_no_go_even_with_product_title():
    ok, reason = evaluate_watchlist(
        "no_go",
        top_score=40,
        top_role_id="ai_product_manager",
        title="Omikron - Product Manager Electronic Banking (m/w/d)",
    )
    assert ok is False
    assert reason == "status_flag=no_go"


def test_watchlist_rejects_strong_score():
    ok, reason = evaluate_watchlist(
        "proceed",
        top_score=88,
        top_role_id="ai_product_manager",
        title="AI Product Manager (m/w/d)",
    )
    assert ok is False
    assert reason is not None
    assert ">=75" in reason


def test_watchlist_rejects_title_deny():
    ok, reason = evaluate_watchlist(
        "proceed",
        top_score=40,
        top_role_id="technical_product_manager",
        title="3C - (Java) Full Stack Engineer (w/m/d)",
    )
    assert ok is False
    assert reason is not None
    assert "title_deny_keyword" in reason


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
            return_value=(
                None,
                {
                    "status_flag": "proceed",
                    "verify_product_ownership": False,
                    "presence_policy": {"level": "ok", "outcome": "allowed"},
                    "top_score": 88,
                    "top_role_id": "ai_product_manager",
                    "passes_default_filter": True,
                },
            ),
        ):
            passed = _process_job(FLEX_JOB_URL, use_playwright=False, fit_check=True)

        with patch(
            "scripts.fetch_jobs_batch._run_fit_check",
            return_value=(
                None,
                {
                    "status_flag": "proceed",
                    "verify_product_ownership": False,
                    "presence_policy": {"level": "ok", "outcome": "allowed"},
                    "top_score": 36,
                    "top_role_id": "technical_product_manager",
                    "passes_default_filter": False,
                    "filter_reject_reason": "top_score=36<75",
                },
            ),
        ):
            rejected = _process_job(FLEX_JOB_URL, use_playwright=False, fit_check=True)

    assert passed["passes_default_filter"] is True
    assert "reject_reason" not in passed
    assert rejected["passes_default_filter"] is False
    assert rejected["reject_reason"] == "filter: top_score=36<75"


def test_prefilter_listings_skips_junk_without_fit_check(board_fixture_html: str):
    from scripts.fetch_jobs_batch import _prefilter_listings

    listings = extract_job_listings_from_html(board_fixture_html, FLEX_BOARD_URL)
    # Drop JSON-only entry without title to avoid network in this unit test
    listings = [item for item in listings if item.title]

    with patch("scripts.fetch_jobs_batch.fetch_job_title") as fetch_title:
        candidates, rejected = _prefilter_listings(listings, use_playwright=False)

    fetch_title.assert_not_called()
    candidate_titles = [item.title for item in candidates]
    assert "AI Product Manager (m/w/d)" in candidate_titles
    assert "Omikron - Product Manager Electronic Banking (m/w/d)" in candidate_titles
    assert all(
        "Engineer" not in (item.title or "") and "Schaden" not in (item.title or "")
        for item in candidates
    )
    assert any(
        row.get("reject_reason", "").startswith("title_prefilter") for row in rejected
    )


def test_limit_applies_after_prefilter(board_fixture_html: str, tmp_path: Path):
    """limit=1 must pick first product-ish title, not first board URL (engineer)."""
    from scripts import fetch_jobs_batch as batch

    listings = extract_job_listings_from_html(board_fixture_html, FLEX_BOARD_URL)
    listings = [item for item in listings if item.title]
    out_path = tmp_path / "batch_out.json"

    def fake_process(url, *, use_playwright, fit_check, listing_title=None):
        return {
            "url": url,
            "status": "ok",
            "title": listing_title,
            "passes_default_filter": True,
            "watchlist": False,
            "sourcing_bucket": "passed",
            "job": {"title": listing_title, "url": url},
            "fit_check": {
                "status_flag": "proceed",
                "top_score": 88,
                "passes_default_filter": True,
            },
        }

    with (
        patch.object(batch, "discover_job_listings", return_value=listings),
        patch.object(batch, "_process_job", side_effect=fake_process) as process_mock,
        patch(
            "sys.argv",
            [
                "fetch_jobs_batch.py",
                "--board-url",
                FLEX_BOARD_URL,
                "--limit",
                "1",
                "--out",
                str(out_path),
            ],
        ),
    ):
        code = batch.main()

    assert code == 0
    assert process_mock.call_count == 1
    processed_title = process_mock.call_args.kwargs.get("listing_title")
    assert processed_title is not None
    assert "Product Manager" in processed_title
    assert "Engineer" not in processed_title
    assert out_path.is_file()


def test_include_weak_proceed_buckets_watchlist(board_fixture_html: str, tmp_path: Path):
    from scripts import fetch_jobs_batch as batch

    listings = extract_job_listings_from_html(board_fixture_html, FLEX_BOARD_URL)
    listings = [item for item in listings if item.title and "AI Product Manager" in item.title]
    out_path = tmp_path / "watchlist_out.json"

    def fake_process(url, *, use_playwright, fit_check, listing_title=None):
        return {
            "url": url,
            "status": "ok",
            "title": listing_title,
            "passes_default_filter": False,
            "watchlist": True,
            "sourcing_bucket": "watchlist",
            "reject_reason": "watchlist: weak_score=32<75",
            "job": {"title": listing_title, "url": url},
            "fit_check": {
                "status_flag": "proceed",
                "top_score": 32,
                "top_role_id": "technical_product_manager",
                "passes_default_filter": False,
                "watchlist_eligible": True,
                "filter_reject_reason": "top_score=32<75",
                "watchlist_reason": "weak_score=32<75",
            },
        }

    with (
        patch.object(batch, "discover_job_listings", return_value=listings),
        patch.object(batch, "_process_job", side_effect=fake_process),
        patch(
            "sys.argv",
            [
                "fetch_jobs_batch.py",
                "--board-url",
                FLEX_BOARD_URL,
                "--include-weak-proceed",
                "--out",
                str(out_path),
            ],
        ),
    ):
        code = batch.main()

    assert code == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["passed_count"] == 0
    assert payload["watchlist_count"] == 1
    assert payload["include_weak_proceed"] is True
    assert payload["watchlist"][0]["title"] == "AI Product Manager (m/w/d)"
    assert payload["watchlist"][0]["reject_reason"].startswith("watchlist:")
    assert all(row["url"] != payload["watchlist"][0]["url"] for row in payload["rejected"])
