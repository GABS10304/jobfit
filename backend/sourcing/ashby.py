"""Ashby job boards via Ashby's official public Job Posting API.

Many funded startups (Skalar's product/engineering roles, for example) post
on Ashby. Ashby publishes a documented, unauthenticated JSON endpoint meant
for exactly this — embedding a company's open roles elsewhere::

    GET https://api.ashbyhq.com/posting-api/job-board/<org>

One request returns every listed job *including the full description*, so
there is no per-job detail fetch: cheaper and gentler than scraping HTML.

Board URL accepted in YAML: ``https://jobs.ashbyhq.com/<org>`` (the public
careers page) — the org slug is taken from it.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

from backend.sourcing.personio import (
    JobListing,
    NormalizedJobDescription,
    _html_to_text,
    _infer_work_mode,
)

API_URL = "https://api.ashbyhq.com/posting-api/job-board/{org}"
BOARD_HOSTS = frozenset({"jobs.ashbyhq.com"})
DEFAULT_TIMEOUT = 30.0
_ORG_RE = re.compile(r"^/([^/?#]+)/?", re.IGNORECASE)
_JOB_RE = re.compile(r"^/([^/?#]+)/([0-9a-f]{8}-[0-9a-f-]{27,})", re.IGNORECASE)
_WORKPLACE = {"onsite": "On-site", "hybrid": "Hybrid", "remote": "Remote"}


def is_ashby_board_url(url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.hostname or "").casefold() in BOARD_HOSTS and bool(
        _ORG_RE.match(parsed.path or "")
    ) and not _JOB_RE.match(parsed.path or "")


def is_ashby_job_url(url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.hostname or "").casefold() in BOARD_HOSTS and bool(
        _JOB_RE.match(parsed.path or "")
    )


def org_from_url(url: str) -> str:
    parsed = urlparse(url)
    match = _ORG_RE.match(parsed.path or "")
    if (parsed.hostname or "").casefold() not in BOARD_HOSTS or not match:
        raise ValueError(f"Not an Ashby board URL: {url}")
    return match.group(1)


def fetch_board_json(org: str, *, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
    headers = {
        "User-Agent": "job-fit-system/1.0 (personal job search; +https://github.com/GABS10304/jobfit)",
        "Accept": "application/json",
    }
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        response = client.get(API_URL.format(org=org))
        response.raise_for_status()
        payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _location(job: dict[str, Any]) -> str | None:
    names: list[str] = []
    primary = job.get("location")
    if isinstance(primary, str) and primary.strip():
        names.append(primary.strip())
    for extra in job.get("secondaryLocations") or []:
        name = extra.get("location") if isinstance(extra, dict) else None
        if isinstance(name, str) and name.strip() and name.strip() not in names:
            names.append(name.strip())
    if job.get("isRemote") and "Remote" not in names:
        names.append("Remote")
    return " / ".join(names) or None


def normalize_job(
    job: dict[str, Any], *, fetched_at: str | None = None
) -> NormalizedJobDescription | None:
    title = str(job.get("title") or "").strip()
    url = str(job.get("jobUrl") or "").strip()
    html = job.get("descriptionHtml")
    jd_text = _html_to_text(html) if isinstance(html, str) and html.strip() else str(
        job.get("descriptionPlain") or ""
    ).strip()
    if not title or not url or not jd_text:
        return None
    location = _location(job)
    # Text first (companies often write "hybrid" in the body while leaving
    # the structured field at its OnSite default); structured field as fallback.
    workplace = _WORKPLACE.get(str(job.get("workplaceType") or "").casefold())
    work_mode = _infer_work_mode(location, jd_text) or workplace
    return NormalizedJobDescription(
        title=title,
        location=location,
        work_mode=work_mode,
        employment_type=str(job.get("employmentType") or "").strip() or None,
        jd_text=jd_text,
        url=url,
        source="ashby",
        fetched_at=fetched_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )


def discover_jobs(
    board_url: str,
    *,
    company: str | None = None,
    fetch_json: Callable[[str], dict[str, Any]] = fetch_board_json,
) -> list[tuple[JobListing, NormalizedJobDescription]]:
    """All listed jobs of one Ashby board as (listing, full JD) pairs."""
    org = org_from_url(board_url)
    payload = fetch_json(org)
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    out: list[tuple[JobListing, NormalizedJobDescription]] = []
    for raw in payload.get("jobs") or []:
        if not isinstance(raw, dict) or raw.get("isListed") is False:
            continue
        job = normalize_job(raw, fetched_at=ts)
        if job is None:
            continue
        out.append(
            (
                JobListing(url=job.url, title=job.title, locations_text=job.location,
                           company=company or org),
                job,
            )
        )
    return out


def fetch_ashby_job(
    url: str, *, fetch_json: Callable[[str], dict[str, Any]] = fetch_board_json
) -> NormalizedJobDescription:
    """Single job by URL (looks it up in its board's API response)."""
    match = _JOB_RE.match(urlparse(url).path or "")
    if not is_ashby_job_url(url) or not match:
        raise ValueError(f"Not an Ashby job URL: {url}")
    org, job_id = match.group(1), match.group(2).casefold()
    for listing, job in discover_jobs(f"https://jobs.ashbyhq.com/{org}", fetch_json=fetch_json):
        if job_id in listing.url.casefold():
            return job
    raise ValueError(f"Ashby job not found on board {org!r}: {url}")
