"""Tests for JOIN (join.com) sourcing, the seen cache and LinkedIn pagination.

Fixtures are inline and synthetic (no network): they mirror the two shapes a
JOIN page can take — server-rendered anchors and Next.js __NEXT_DATA__ — plus
Google-for-Jobs JSON-LD on detail pages.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from backend.generation.watchlist_cv import job_id_from_url
from backend.sourcing import join
from backend.sourcing.personio import JobListing
from backend.tracking.seen_cache import SeenCache, job_key

BOARD = "https://join.com/companies/skalar"

BOARD_PAGE_1 = """
<html><body><main>
  <a href="/companies/skalar/16804866-account-executive-w-m-d?pid=x">
    <h3>Account Executive (w/m/d)</h3><span>Munich, Germany</span></a>
  <a href="https://join.com/companies/skalar/16900001-senior-product-manager-m-w-d">
    <h3>Senior Product Manager (m/w/d)</h3><span>Munich, Germany</span></a>
  <a href="/companies/skalar/16900001-senior-product-manager-m-w-d">duplicate</a>
  <a href="/companies/othercorp/111111-foreign-job">Foreign</a>
</main></body></html>
"""

NEXT_DATA = {
    "props": {"pageProps": {"jobs": {"items": [
        {"id": 16804820, "idParam": "16804820-product-engineer-w-m-d",
         "title": "Product Engineer (w/m/d)",
         "city": {"cityName": "Munich", "countryName": "Germany"}},
        {"id": 16900001, "title": "Senior Product Manager (m/w/d)"},
        {"id": 7, "title": "Category, not a job"},
    ]}}}
}
BOARD_PAGE_2 = (
    '<html><body><script id="__NEXT_DATA__" type="application/json">'
    + json.dumps(NEXT_DATA)
    + "</script></body></html>"
)

JOB_URL = "https://join.com/companies/skalar/16900001-senior-product-manager-m-w-d"

JOB_LD = {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    "title": "Senior Product Manager (m/w/d)",
    "description": "<p>Du verantwortest KI-Features end-to-end.</p><ul><li>RAG &amp; Evals</li></ul>",
    "employmentType": ["FULL_TIME"],
    "hiringOrganization": {"@type": "Organization", "name": "Skalar"},
    "jobLocation": [{"@type": "Place", "address": {
        "addressLocality": "München", "addressCountry": "DE"}}],
}


def _page(ld: dict | None = None, next_data: dict | None = None, body: str = "") -> str:
    parts = ["<html><head>"]
    if ld is not None:
        parts.append(f'<script type="application/ld+json">{json.dumps(ld)}</script>')
    parts.append("</head><body>")
    if next_data is not None:
        parts.append(
            f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script>'
        )
    parts.append(body + "</body></html>")
    return "".join(parts)


# ------------------------------------------------------------------------- URLs


def test_url_detection_and_normalization():
    assert join.is_join_board_url(BOARD)
    assert join.is_join_board_url(BOARD + "/")
    assert not join.is_join_board_url(JOB_URL)
    assert join.is_join_job_url(JOB_URL)
    assert not join.is_join_job_url("https://skalar.jobs.personio.de/job/123")
    assert join.normalize_board_url("https://www.join.com/companies/Skalar?page=3") == BOARD
    assert join.board_page_url(BOARD, 1) == BOARD
    assert join.board_page_url(BOARD, 2) == BOARD + "?page=2"
    with pytest.raises(ValueError):
        join.normalize_board_url("https://example.com/companies/skalar")


def test_job_ids_are_stable_for_state_store():
    assert join.job_id_from_join_url(JOB_URL) == "16900001"
    assert job_id_from_url(JOB_URL) == "16900001"
    # Personio / LinkedIn patterns still win for their own URLs.
    assert job_id_from_url("https://x.jobs.personio.de/job/42") == "42"


# ----------------------------------------------------------------------- board


def test_board_anchors_dedup_and_ignore_other_companies():
    listings = join.extract_job_listings_from_html(BOARD_PAGE_1, BOARD, company="Skalar")
    assert [l.title for l in listings] == [
        "Account Executive (w/m/d)",
        "Senior Product Manager (m/w/d)",
    ]
    assert all(l.company == "Skalar" for l in listings)
    assert "?" not in listings[0].url
    assert listings[0].url == "https://join.com/companies/skalar/16804866-account-executive-w-m-d"


def test_board_next_data_fallback():
    listings = join.extract_job_listings_from_html(BOARD_PAGE_2, BOARD)
    by_id = {join.job_id_from_join_url(l.url): l for l in listings}
    assert set(by_id) == {"16804820", "16900001"}  # small "7" id ignored
    assert by_id["16804820"].url.endswith("/16804820-product-engineer-w-m-d")
    assert by_id["16804820"].locations_text == "Munich, Germany"


def test_discover_walks_pages_until_no_new_ids():
    pages = {
        BOARD: BOARD_PAGE_1,
        BOARD + "?page=2": BOARD_PAGE_2,
        BOARD + "?page=3": BOARD_PAGE_2,  # repeats → stop
    }
    calls: list[str] = []

    def fake_fetch(url: str) -> str:
        calls.append(url)
        return pages.get(url, "<html></html>")

    listings = join.discover_job_listings(BOARD, company="Skalar", fetch=fake_fetch)
    ids = [join.job_id_from_join_url(l.url) for l in listings]
    assert ids == ["16804866", "16900001", "16804820"]
    assert calls == [BOARD, BOARD + "?page=2", BOARD + "?page=3"]


def test_discover_respects_max_pages():
    calls: list[str] = []

    def fake_fetch(url: str) -> str:
        calls.append(url)
        n = len(calls)
        return f'<a href="/companies/skalar/{100000 + n}-job"><h3>Job {n}</h3></a>'

    listings = join.discover_job_listings(BOARD, max_pages=3, fetch=fake_fetch)
    assert len(listings) == 3 and len(calls) == 3


# ------------------------------------------------------------------------- job


def test_parse_job_prefers_json_ld():
    job, company = join.parse_join_html(_page(ld=JOB_LD), JOB_URL)
    assert job.title == "Senior Product Manager (m/w/d)"
    assert job.source == "join"
    assert job.location == "München, DE"
    assert job.employment_type == "FULL_TIME"
    assert "KI-Features" in job.jd_text and "RAG & Evals" in job.jd_text
    assert "<" not in job.jd_text
    assert company == "Skalar"


def test_parse_job_json_ld_inside_graph():
    ld = {"@context": "https://schema.org", "@graph": [{"@type": "WebPage"}, JOB_LD]}
    job, _ = join.parse_join_html(_page(ld=ld), JOB_URL)
    assert job.title == "Senior Product Manager (m/w/d)"


def test_parse_job_next_data_fallback():
    data = {"props": {"pageProps": {"job": {
        "id": 16900001,
        "title": "Senior Product Manager (m/w/d)",
        "description": "<p>Hybrid in München. LLM-Features in Produktion.</p>",
        "company": {"name": "Skalar"},
        "city": {"cityName": "Munich", "countryName": "Germany"},
    }}}}
    job, company = join.parse_join_html(_page(next_data=data), JOB_URL)
    assert job.title == "Senior Product Manager (m/w/d)"
    assert job.work_mode == "Hybrid"
    assert company == "Skalar"
    assert job.location == "Munich, Germany"


def test_parse_job_dom_fallback_and_failure():
    body = "<main><h1>Product Owner KI</h1><p>" + ("Aufgaben und Profil. " * 20) + "</p></main>"
    job, company = join.parse_join_html(_page(body=body), JOB_URL)
    assert job.title == "Product Owner KI" and company is None
    with pytest.raises(ValueError):
        join.parse_join_html("<html><body><h1>Nur Navigation</h1></body></html>", JOB_URL)


def test_fetch_join_job_rejects_non_join_url():
    with pytest.raises(ValueError):
        join.fetch_join_job("https://example.com/job/1", fetch=lambda u: "")


# ------------------------------------------------------------------ seen cache


def test_seen_cache_ttl_and_roundtrip(tmp_path: Path):
    path = tmp_path / "seen.json"
    cache = SeenCache(path, today=date(2026, 10, 17))
    assert not cache.is_fresh(JOB_URL)
    cache.mark(JOB_URL)
    assert cache.is_fresh(JOB_URL)
    # Same job under a different slug/query is the same key.
    assert cache.is_fresh("https://join.com/companies/skalar/16900001?x=1")
    cache.save()

    later = SeenCache(path, today=date(2026, 11, 5))  # 19 days later
    assert not later.is_fresh(JOB_URL, ttl_days=14)
    assert later.is_fresh(JOB_URL, ttl_days=30)
    assert not later.is_fresh(JOB_URL, ttl_days=0)


def test_seen_cache_prunes_old_entries(tmp_path: Path):
    path = tmp_path / "seen.json"
    path.write_text(json.dumps({"1": "2026-01-01", "2": "2026-10-01", "3": "garbage"}))
    cache = SeenCache(path, today=date(2026, 10, 17))
    cache.save()
    assert json.loads(path.read_text()) == {"2": "2026-10-01"}


def test_job_key_falls_back_to_url():
    assert job_key("https://example.com/careers/foo/?a=1") == "https://example.com/careers/foo"


# ----------------------------------------------------------- LinkedIn paging


def test_linkedin_run_search_pages_and_skips_seen(monkeypatch, tmp_path: Path):
    from scripts import fetch_jobs_linkedin_search as runner

    def listing(i: int) -> JobListing:
        return JobListing(url=f"https://www.linkedin.com/jobs/view/{4000000 + i}",
                          title="Senior Product Manager (m/w/d)", company=f"Co{i}")

    pages = {1: [listing(i) for i in range(10)], 2: [listing(i) for i in range(10, 13)]}
    requested: list[int] = []

    def fake_search(**kwargs):
        requested.append(kwargs["page"])
        return pages.get(kwargs["page"], [])

    fetched: list[str] = []

    def fake_process(url, **kwargs):
        fetched.append(url)
        return {"url": url, "status": "ok", "title": kwargs.get("listing_title"),
                "sourcing_bucket": "rejected", "passes_default_filter": False}

    monkeypatch.setattr(runner.linkedin, "search_jobs", fake_search)
    monkeypatch.setattr(runner, "_process_job", fake_process)

    seen = SeenCache(tmp_path / "seen.json", today=date(2026, 10, 17))
    seen.mark(listing(0).url)

    result = runner.run_search(query="Product Manager", location="Germany", jobage_days=3,
                               remote=None, limit=None, fit_check=True, delay=0,
                               pages=3, seen=seen)

    assert requested == [1, 2]  # page 2 was short → page 3 never requested
    assert result["discovered"] == 13
    assert result["skipped_seen"] == 1
    assert len(fetched) == 12 and listing(0).url not in fetched
    assert all(seen.is_fresh(u) for u in fetched)  # newly checked jobs are remembered
