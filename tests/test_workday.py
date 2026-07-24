"""Tests for Workday JD fetch/parser and CXS board discovery."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.sourcing.personio import NormalizedJobDescription
from backend.sourcing.workday import (
    discover_job_listings,
    discover_job_urls,
    fetch_workday_job,
    is_workday_board_url,
    is_workday_job_url,
    listings_from_cxs_payload,
    parse_workday_board_url,
    parse_workday_html,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_HTML = REPO_ROOT / "tests" / "fixtures" / "workday_ing_prozessmanager.html"
FIXTURE_DOM_HTML = REPO_ROOT / "tests" / "fixtures" / "workday_ing_dom_only.html"
CXS_PAGE0 = REPO_ROOT / "tests" / "fixtures" / "workday_cxs_ing_page0.json"
CXS_PAGE1 = REPO_ROOT / "tests" / "fixtures" / "workday_cxs_ing_page1.json"
ING_BOARD = "https://ing.wd3.myworkdayjobs.com/de-DE/ICSGBLCOR"
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


@pytest.fixture
def cxs_page0() -> dict:
    return json.loads(CXS_PAGE0.read_text(encoding="utf-8"))


@pytest.fixture
def cxs_page1() -> dict:
    return json.loads(CXS_PAGE1.read_text(encoding="utf-8"))


def test_is_workday_job_url():
    assert is_workday_job_url(ING_URL)
    assert is_workday_job_url(
        "https://example.wd5.myworkdayjobs.com/en-US/Careers/job/Berlin/Role_REQ-1"
    )
    assert not is_workday_job_url(
        "https://flex-capital-management-gmbh.jobs.personio.de/job/2689046"
    )
    assert not is_workday_job_url(ING_BOARD)


def test_is_workday_board_url():
    assert is_workday_board_url(ING_BOARD)
    assert is_workday_board_url("https://pg.wd5.myworkdayjobs.com/en-US/1000")
    assert is_workday_board_url("https://acme.wd1.myworkdayjobs.com/External")
    assert not is_workday_board_url(ING_URL)
    assert not is_workday_board_url(
        "https://flex-capital-management-gmbh.jobs.personio.de/"
    )


def test_parse_workday_board_url():
    board = parse_workday_board_url(ING_BOARD)
    assert board.tenant == "ing"
    assert board.site == "ICSGBLCOR"
    assert board.locale == "de-DE"
    assert board.origin == "https://ing.wd3.myworkdayjobs.com"
    assert board.cxs_jobs_url == (
        "https://ing.wd3.myworkdayjobs.com/wday/cxs/ing/ICSGBLCOR/jobs"
    )
    assert board.job_url("/job/Nrnberg/Role_REQ-1").endswith(
        "/de-DE/ICSGBLCOR/job/Nrnberg/Role_REQ-1"
    )


def test_listings_from_cxs_payload(cxs_page0: dict):
    board = parse_workday_board_url(ING_BOARD)
    listings = listings_from_cxs_payload(cxs_page0, board)
    assert len(listings) == 3
    assert listings[0].title == "Contractor - Regulatory Test Lead"
    assert listings[1].title == "AI Product Manager"
    assert listings[1].url == (
        "https://ing.wd3.myworkdayjobs.com/de-DE/ICSGBLCOR/job/Nrnberg/"
        "AI-Product-Manager_REQ-TEST-1"
    )


def test_discover_job_listings_paginates_mocked_cxs(cxs_page0: dict, cxs_page1: dict):
    pages = {0: cxs_page0, 3: cxs_page1}

    def fake_fetch(board, *, offset, limit, search_text):
        assert board.tenant == "ing"
        assert limit <= 20
        return pages.get(offset, {"total": 7, "jobPostings": []})

    listings = discover_job_listings(
        ING_BOARD, page_size=3, fetch_page=fake_fetch
    )
    assert len(listings) == 5
    titles = [item.title for item in listings]
    assert "AI Product Manager" in titles
    assert "Senior Product Manager Platform" in titles
    assert "HR Business Partner" in titles

    urls = discover_job_urls(ING_BOARD, max_results=2, page_size=3, fetch_page=fake_fetch)
    assert len(urls) == 2
    assert all("/job/" in url for url in urls)


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


@pytest.mark.network
def test_discover_job_urls_live_cxs_smoke():
    try:
        urls = discover_job_urls(ING_BOARD, max_results=5, search_text="Product")
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"network unavailable or CXS unreachable: {exc}")
    assert len(urls) == 5
    assert all(is_workday_job_url(url) for url in urls)
    assert all("ICSGBLCOR" in url for url in urls)
