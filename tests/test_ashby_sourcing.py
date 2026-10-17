"""Tests for Ashby sourcing (backend.sourcing.ashby + multi-board runner).

Fixture mirrors the field names of Ashby's public Job Posting API
(api.ashbyhq.com/posting-api/job-board/<org>), verified against Skalar's
live board in Okt 2026. No network.
"""

from __future__ import annotations

import pytest

from backend.generation.watchlist_cv import job_id_from_url
from backend.sourcing import ashby
from backend.tracking.state_store import make_job_id

BOARD = "https://jobs.ashbyhq.com/skalar"
PM_URL = "https://jobs.ashbyhq.com/skalar/9d2d68c1-ca7b-4052-bda0-d2f6b6fe553e"

PAYLOAD = {
    "jobs": [
        {
            "id": "9d2d68c1-ca7b-4052-bda0-d2f6b6fe553e",
            "title": "Senior Product Manager (m/w/d)",
            "department": "Product", "team": "Product",
            "employmentType": "FullTime",
            "location": "München", "secondaryLocations": [],
            "publishedAt": "2026-10-01T10:00:00.000+00:00",
            "isListed": True, "isRemote": False, "workplaceType": "OnSite",
            "address": {"postalAddress": {"addressLocality": "München", "addressCountry": "DE"}},
            "jobUrl": PM_URL,
            "applyUrl": PM_URL + "/application",
            "descriptionHtml": "<p>KI-Features end-to-end.</p><ul><li>Evals &amp; RAG</li></ul>"
                               "<p>Hybrid: Home Office und Büro in München.</p>",
            "descriptionPlain": "KI-Features end-to-end.",
        },
        {
            "id": "cde4a728-a388-47da-b1c3-d307398ec23e",
            "title": "Senior AI Engineer (w/m/d)", "employmentType": "FullTime",
            "location": "München", "isListed": True, "isRemote": False,
            "workplaceType": "OnSite",
            "jobUrl": "https://jobs.ashbyhq.com/skalar/cde4a728-a388-47da-b1c3-d307398ec23e",
            "descriptionHtml": "<p>Build agents.</p>",
        },
        {
            "id": "dd3fb9a9-29bf-4d45-a091-368c3ec61aad",
            "title": "Head of Tax (w/m/d)", "location": "München",
            "secondaryLocations": [{"location": "Berlin"}],
            "isListed": True, "isRemote": True, "workplaceType": "Hybrid",
            "jobUrl": "https://jobs.ashbyhq.com/skalar/dd3fb9a9-29bf-4d45-a091-368c3ec61aad",
            "descriptionPlain": "Leite das Steuerteam.",
        },
        {"id": "x", "title": "Hidden", "isListed": False,
         "jobUrl": "https://jobs.ashbyhq.com/skalar/11111111-2222-3333-4444-555555555555",
         "descriptionPlain": "nope"},
        {"id": "y", "title": "", "jobUrl": "", "descriptionPlain": ""},
    ]
}


def fake_fetch(org: str) -> dict:
    assert org == "skalar"
    return PAYLOAD


def test_url_detection():
    assert ashby.is_ashby_board_url(BOARD)
    assert ashby.is_ashby_board_url(BOARD + "/")
    assert not ashby.is_ashby_board_url(PM_URL)
    assert ashby.is_ashby_job_url(PM_URL)
    assert not ashby.is_ashby_job_url("https://join.com/companies/skalar/123-x")
    assert ashby.org_from_url(PM_URL) == "skalar"
    with pytest.raises(ValueError):
        ashby.org_from_url("https://example.com/skalar")


def test_discover_skips_unlisted_and_empty_and_normalizes():
    pairs = ashby.discover_jobs(BOARD, company="Skalar", fetch_json=fake_fetch)
    titles = [listing.title for listing, _ in pairs]
    assert titles == ["Senior Product Manager (m/w/d)", "Senior AI Engineer (w/m/d)",
                      "Head of Tax (w/m/d)"]
    listing, job = pairs[0]
    assert listing.company == "Skalar" and listing.url == PM_URL
    assert job.source == "ashby"
    assert "Evals & RAG" in job.jd_text and "<" not in job.jd_text
    # Body says hybrid → beats the structured OnSite default.
    assert job.work_mode == "Hybrid"
    head_of_tax = pairs[2][1]
    assert head_of_tax.location == "München / Berlin / Remote"
    assert head_of_tax.jd_text == "Leite das Steuerteam."  # plain-text fallback


def test_structured_workplace_used_when_text_is_silent():
    _, engineer = ashby.discover_jobs(BOARD, fetch_json=fake_fetch)[1]
    assert engineer.work_mode == "On-site"


def test_fetch_single_job_by_url():
    job = ashby.fetch_ashby_job(PM_URL, fetch_json=fake_fetch)
    assert job.title == "Senior Product Manager (m/w/d)"
    with pytest.raises(ValueError):
        ashby.fetch_ashby_job(
            "https://jobs.ashbyhq.com/skalar/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            fetch_json=fake_fetch,
        )


def test_job_ids_distinguish_companies_with_same_title():
    assert job_id_from_url(PM_URL) == "9d2d68c1"
    other = "https://jobs.ashbyhq.com/othercorp/0f0f0f0f-1111-2222-3333-444444444444"
    title = "Senior Product Manager (m/w/d)"
    assert make_job_id(url=PM_URL, title=title) != make_job_id(url=other, title=title)


def test_runner_buckets_and_prefilters():
    from scripts import fetch_jobs_multi_ashby as runner

    board = {"id": "skalar", "name": "Skalar", "url": BOARD}
    result = runner.process_board(
        board, fit_check=True, excluded_companies=None,
        discover=lambda url, company: ashby.discover_jobs(url, company=company,
                                                          fetch_json=fake_fetch),
    )
    assert result["status"] == "ok" and result["discovered"] == 3
    assert result["fit_checked"] == 1  # only the PM survives the title prefilter
    pm_rows = [r for r in result["passed"] + result["watchlist"] + result["rejected"]
               if r["url"] == PM_URL]
    assert pm_rows and pm_rows[0]["company"] == "Skalar"
    assert "fit_check" in pm_rows[0]


def test_runner_skips_excluded_and_survives_errors():
    from scripts import fetch_jobs_multi_ashby as runner

    board = {"id": "skalar", "name": "Skalar", "url": BOARD}
    skipped = runner.process_board(board, fit_check=True, excluded_companies=["Skalar"])
    assert skipped["status"] == "skipped"

    def boom(url, company):
        raise RuntimeError("HTTP 503")

    errored = runner.process_board(board, fit_check=True, excluded_companies=None, discover=boom)
    assert errored["status"] == "error" and "503" in errored["error"]
