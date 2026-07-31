"""Tests for LinkedIn guest-search parsing (backend.sourcing.linkedin)."""

from __future__ import annotations

from pathlib import Path

from backend.generation.watchlist_cv import job_id_from_url
from backend.sourcing.linkedin import (
    job_id_from_linkedin_url,
    jobage_to_tpr,
    parse_job_cards,
    parse_job_detail,
    work_type_flag,
)
from backend.sourcing.personio import NormalizedJobDescription

REPO_ROOT = Path(__file__).resolve().parent.parent
SEARCH_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "linkedin_search_results.html"
DETAIL_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "linkedin_job_detail.html"


def test_parse_job_cards_extracts_all_fields():
    html = SEARCH_FIXTURE.read_text(encoding="utf-8")
    cards = parse_job_cards(html)

    assert len(cards) == 2
    first = cards[0]
    assert first.title == "AI Product Manager (m/w/d)"
    assert first.company == "TestCo GmbH"
    assert first.locations_text == "Berlin, Germany"
    assert first.url == "https://www.linkedin.com/jobs/view/ai-product-manager-at-testco-4426311357"


def test_parse_job_cards_strips_tracking_query_params():
    html = SEARCH_FIXTURE.read_text(encoding="utf-8")
    cards = parse_job_cards(html)
    assert "?" not in cards[0].url


def test_parse_job_detail_extracts_normalized_job():
    html = DETAIL_FIXTURE.read_text(encoding="utf-8")
    job, company = parse_job_detail(html, "4426311357")

    assert isinstance(job, NormalizedJobDescription)
    assert job.title == "AI Product Manager (m/w/d)"
    assert job.location == "Berlin, Germany"
    assert job.employment_type == "Full-time"
    assert job.source == "linkedin"
    assert job.url == "https://www.linkedin.com/jobs/view/4426311357"
    assert company == "TestCo GmbH"


def test_parse_job_detail_preserves_paragraph_breaks():
    html = DETAIL_FIXTURE.read_text(encoding="utf-8")
    job, _ = parse_job_detail(html, "4426311357")

    assert "\n\n" in job.jd_text
    assert "Python and LLM experience required." in job.jd_text
    assert "<" not in job.jd_text


def test_jobage_to_tpr():
    assert jobage_to_tpr(1) == "r86400"
    assert jobage_to_tpr(7) == "r604800"
    assert jobage_to_tpr(None) is None
    assert jobage_to_tpr(0) is None


def test_work_type_flag():
    assert work_type_flag("remote") == "2"
    assert work_type_flag("hybrid") == "3"
    assert work_type_flag("onsite") == "1"
    assert work_type_flag(None) is None
    assert work_type_flag("unknown") is None


def test_job_id_from_linkedin_url_handles_slug_and_bare_forms():
    assert (
        job_id_from_linkedin_url(
            "https://www.linkedin.com/jobs/view/ai-product-manager-at-testco-4426311357"
        )
        == "4426311357"
    )
    assert job_id_from_linkedin_url("https://www.linkedin.com/jobs/view/4426311357") == "4426311357"


def test_shared_job_id_from_url_recognizes_linkedin_urls():
    job_id = job_id_from_url(
        "https://www.linkedin.com/jobs/view/ai-product-manager-at-testco-4426311357"
    )
    assert job_id == "4426311357"


def test_shared_job_id_from_url_still_recognizes_personio_urls():
    job_id = job_id_from_url("https://flex.jobs.personio.de/job/2689046?language=de")
    assert job_id == "2689046"
