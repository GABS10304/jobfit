"""Fetch and parse JOIN (join.com) company boards and job pages.

JOIN is the ATS of choice for many DACH startups (e.g. Skalar, Munich) that
never show up on Personio/Workday. Each company has a public, paginated
careers page::

    https://join.com/companies/<slug>            (page 1)
    https://join.com/companies/<slug>?page=2     (page 2, ...)

Job detail URLs follow ``/companies/<slug>/<numeric-id>-<title-slug>``.

Parsing is deliberately layered because JOIN is a Next.js app and its markup
can shift without notice:

1. ``application/ld+json`` JobPosting (Google-for-Jobs markup) — preferred
2. ``__NEXT_DATA__`` JSON — walk for a job-shaped object
3. Plain DOM text (``<h1>`` + body text) — last resort

Same polite defaults as the other public-board adapters: honest UA, low
volume, curated board list in ``domain/join_boards.yaml``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from html import unescape
from typing import Any
from urllib.parse import urlparse

import httpx

from backend.sourcing.personio import (
    JobListing,
    NormalizedJobDescription,
    _html_to_text,
    _infer_work_mode,
    fetch_page_html,
)

JOIN_HOSTS = frozenset({"join.com", "www.join.com"})
DEFAULT_MAX_PAGES = 10
_SLUG_RE = re.compile(r"^/companies/([^/?#]+)/?$", re.IGNORECASE)
_JOB_PATH_RE = re.compile(r"^/companies/([^/?#]+)/(\d+)(?:-[^/?#]*)?/?$", re.IGNORECASE)
_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_LD_JSON_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


# --------------------------------------------------------------------------- URLs


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").casefold()


def is_join_board_url(url: str) -> bool:
    parsed = urlparse(url)
    return _host(url) in JOIN_HOSTS and bool(_SLUG_RE.match(parsed.path or ""))


def is_join_job_url(url: str) -> bool:
    parsed = urlparse(url)
    return _host(url) in JOIN_HOSTS and bool(_JOB_PATH_RE.match(parsed.path or ""))


def company_slug(url: str) -> str | None:
    path = urlparse(url).path or ""
    match = _JOB_PATH_RE.match(path) or _SLUG_RE.match(path)
    return match.group(1).casefold() if match else None


def normalize_board_url(url: str) -> str:
    slug = company_slug(url)
    if _host(url) not in JOIN_HOSTS or not slug:
        raise ValueError(f"Not a JOIN company board URL: {url}")
    return f"https://join.com/companies/{slug}"


def board_page_url(board_url: str, page: int) -> str:
    base = normalize_board_url(board_url)
    return base if page <= 1 else f"{base}?page={page}"


def canonical_job_url(slug: str, job_id: str, title_slug: str | None = None) -> str:
    tail = f"{job_id}-{title_slug}" if title_slug else job_id
    return f"https://join.com/companies/{slug}/{tail}"


# ------------------------------------------------------------------ board parsing


def _anchor_re(slug: str) -> re.Pattern[str]:
    return re.compile(
        r'<a[^>]+href=["\']((?:https?://(?:www\.)?join\.com)?/companies/'
        + re.escape(slug)
        + r'/(\d+)(?:-([a-z0-9\-]*))?)(?:[?#][^"\']*)?["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )


def _title_from_anchor(inner_html: str) -> str | None:
    heading = re.search(r"<h[1-4][^>]*>(.*?)</h[1-4]>", inner_html, re.IGNORECASE | re.DOTALL)
    text = _html_to_text(heading.group(1) if heading else inner_html).strip()
    if not text:
        return None
    first = re.split(r"\n", text, maxsplit=1)[0].strip()
    return first or None


def _iter_dicts(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_dicts(item)


def _next_data(html: str) -> Any | None:
    match = _NEXT_DATA_RE.search(html)
    if not match:
        return None
    try:
        return json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        return None


def _city_text(job: dict[str, Any]) -> str | None:
    city = job.get("city")
    if isinstance(city, dict):
        parts = [city.get("cityName") or city.get("name"), city.get("countryName")]
        text = ", ".join(str(p) for p in parts if p)
        return text or None
    if isinstance(city, str) and city.strip():
        return city.strip()
    location = job.get("location")
    if isinstance(location, str) and location.strip():
        return location.strip()
    return None


def _listings_from_next_data(data: Any, slug: str) -> list[JobListing]:
    """Job objects in JOIN's page props carry at least ``id`` + ``title``."""
    listings: list[JobListing] = []
    for node in _iter_dicts(data):
        job_id = node.get("id") or node.get("jobId")
        title = node.get("title")
        if not (isinstance(title, str) and title.strip()):
            continue
        if not (isinstance(job_id, int) or (isinstance(job_id, str) and job_id.isdigit())):
            continue
        job_id = str(job_id)
        if len(job_id) < 5:  # skip unrelated small ids (categories etc.)
            continue
        title_slug = node.get("idParam") or node.get("slug")
        if isinstance(title_slug, str) and title_slug.startswith(f"{job_id}-"):
            title_slug = title_slug[len(job_id) + 1 :]
        elif not isinstance(title_slug, str):
            title_slug = None
        listings.append(
            JobListing(
                url=canonical_job_url(slug, job_id, title_slug),
                title=title.strip(),
                locations_text=_city_text(node),
            )
        )
    return listings


def extract_job_listings_from_html(
    html: str, board_url: str, *, company: str | None = None
) -> list[JobListing]:
    """Unique job listings (URL + title) from one JOIN board page."""
    slug = company_slug(board_url)
    if not slug:
        raise ValueError(f"Not a JOIN company board URL: {board_url}")

    seen: set[str] = set()
    listings: list[JobListing] = []

    def _add(listing: JobListing) -> None:
        job_id = job_id_from_join_url(listing.url)
        if not job_id or job_id in seen:
            return
        seen.add(job_id)
        listings.append(
            JobListing(
                url=listing.url,
                title=listing.title,
                locations_text=listing.locations_text,
                company=company or listing.company,
            )
        )

    for match in _anchor_re(slug).finditer(html):
        job_id, title_slug, inner = match.group(2), match.group(3), match.group(4)
        _add(
            JobListing(
                url=canonical_job_url(slug, job_id, title_slug or None),
                title=_title_from_anchor(inner),
            )
        )

    data = _next_data(html)
    if data is not None:
        for listing in _listings_from_next_data(data, slug):
            job_id = job_id_from_join_url(listing.url)
            if job_id in seen:
                # Fill a missing anchor title from structured data.
                for i, existing in enumerate(listings):
                    if job_id_from_join_url(existing.url) == job_id and not existing.title:
                        listings[i] = JobListing(
                            url=existing.url,
                            title=listing.title,
                            locations_text=existing.locations_text or listing.locations_text,
                            company=existing.company,
                        )
                continue
            _add(listing)

    return listings


def job_id_from_join_url(url: str) -> str | None:
    match = _JOB_PATH_RE.match(urlparse(url).path or "")
    return match.group(2) if match else None


def discover_job_listings(
    board_url: str,
    *,
    company: str | None = None,
    max_pages: int = DEFAULT_MAX_PAGES,
    fetch: Callable[[str], str] = fetch_page_html,
) -> list[JobListing]:
    """Walk ``?page=N`` until a page adds no new job ids (or ``max_pages``)."""
    all_listings: list[JobListing] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        html = fetch(board_page_url(board_url, page))
        new = [
            listing
            for listing in extract_job_listings_from_html(html, board_url, company=company)
            if job_id_from_join_url(listing.url) not in seen
        ]
        if not new:
            break
        for listing in new:
            seen.add(job_id_from_join_url(listing.url) or listing.url)
        all_listings.extend(new)
    return all_listings


# ------------------------------------------------------------------ job parsing


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _job_posting_ld(html: str) -> dict[str, Any] | None:
    for block in _LD_JSON_RE.findall(html):
        try:
            payload = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        for node in _iter_dicts(payload):
            node_type = node.get("@type")
            types = node_type if isinstance(node_type, list) else [node_type]
            if "JobPosting" in types:
                return node
    return None


def _ld_location(data: dict[str, Any]) -> str | None:
    raw = data.get("jobLocation")
    items = raw if isinstance(raw, list) else [raw]
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        address = item.get("address")
        if isinstance(address, dict):
            locality = address.get("addressLocality")
            country = address.get("addressCountry")
            if isinstance(country, dict):
                country = country.get("name")
            text = ", ".join(str(p) for p in (locality, country) if p)
            if text and text not in parts:
                parts.append(text)
    if str(data.get("jobLocationType") or "").upper() == "TELECOMMUTE":
        parts.append("Remote")
    return " / ".join(parts) or None


def _ld_employment(data: dict[str, Any]) -> str | None:
    raw = data.get("employmentType")
    if isinstance(raw, list):
        values = [str(v).strip() for v in raw if str(v).strip()]
        return ", ".join(values) or None
    return str(raw).strip() or None if raw else None


def _ld_company(data: dict[str, Any]) -> str | None:
    org = data.get("hiringOrganization")
    if isinstance(org, dict) and org.get("name"):
        return str(org["name"]).strip() or None
    return None


def _from_ld(data: dict[str, Any], url: str, ts: str) -> tuple[NormalizedJobDescription, str | None] | None:
    title = unescape(str(data.get("title") or "")).strip()
    description = str(data.get("description") or "")
    if not title or not description.strip():
        return None
    jd_text = _html_to_text(description)
    location = _ld_location(data)
    return (
        NormalizedJobDescription(
            title=title,
            location=location,
            work_mode=_infer_work_mode(location, jd_text),
            employment_type=_ld_employment(data),
            jd_text=jd_text,
            url=url,
            source="join",
            fetched_at=ts,
        ),
        _ld_company(data),
    )


def _from_next_data(html: str, url: str, ts: str) -> tuple[NormalizedJobDescription, str | None] | None:
    data = _next_data(html)
    if data is None:
        return None
    wanted_id = job_id_from_join_url(url)
    text_keys = ("description", "jobDescription", "content", "html")

    def _text_len(node: dict[str, Any]) -> int:
        return sum(len(node[k]) for k in text_keys if isinstance(node.get(k), str))

    best: dict[str, Any] | None = None
    for node in _iter_dicts(data):
        title = node.get("title")
        if not (isinstance(title, str) and title.strip()) or not _text_len(node):
            continue
        if wanted_id and str(node.get("id") or "") == wanted_id:
            best = node
            break
        if best is None or _text_len(node) > _text_len(best):
            best = node
    if best is None:
        return None
    body = "\n\n".join(str(best[k]) for k in text_keys if isinstance(best.get(k), str))
    jd_text = _html_to_text(body)
    if not jd_text:
        return None
    company = None
    comp = best.get("company")
    if isinstance(comp, dict):
        company = comp.get("name")
    location = _city_text(best)
    return (
        NormalizedJobDescription(
            title=best["title"].strip(),
            location=location,
            work_mode=_infer_work_mode(location, jd_text),
            employment_type=str(best.get("employmentType") or "").strip() or None,
            jd_text=jd_text,
            url=url,
            source="join",
            fetched_at=ts,
        ),
        company,
    )


def _from_dom(html: str, url: str, ts: str) -> tuple[NormalizedJobDescription, str | None] | None:
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
    title = _html_to_text(h1.group(1)).strip() if h1 else ""
    if not title:
        return None
    main = re.search(r"<main[^>]*>(.*?)</main>", html, re.IGNORECASE | re.DOTALL)
    body = main.group(1) if main else html
    body = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", body, flags=re.I | re.S)
    jd_text = _html_to_text(body)
    if len(jd_text) < 200:  # nav-only shell → not a real JD
        return None
    return (
        NormalizedJobDescription(
            title=title,
            location=None,
            work_mode=_infer_work_mode(None, jd_text),
            employment_type=None,
            jd_text=jd_text,
            url=url,
            source="join",
            fetched_at=ts,
        ),
        None,
    )


def parse_join_html(
    html: str, url: str, fetched_at: str | None = None
) -> tuple[NormalizedJobDescription, str | None]:
    """Parse a JOIN job page → (normalized JD, company name or None)."""
    ts = fetched_at or _utc_now_iso()
    ld = _job_posting_ld(html)
    for parsed in (
        _from_ld(ld, url, ts) if ld else None,
        _from_next_data(html, url, ts),
        _from_dom(html, url, ts),
    ):
        if parsed:
            return parsed
    raise ValueError("Could not parse JOIN job page (JSON-LD, __NEXT_DATA__ and DOM failed)")


def fetch_join_job(
    url: str, *, fetch: Callable[[str], str] = fetch_page_html
) -> tuple[NormalizedJobDescription, str | None]:
    if not is_join_job_url(url):
        raise ValueError(f"Not a JOIN job URL: {url}")
    return parse_join_html(fetch(url), url)


__all__ = [
    "discover_job_listings",
    "extract_job_listings_from_html",
    "fetch_join_job",
    "is_join_board_url",
    "is_join_job_url",
    "job_id_from_join_url",
    "normalize_board_url",
    "parse_join_html",
]

# httpx re-exported for callers that catch HTTPStatusError from fetch_page_html.
HTTPStatusError = httpx.HTTPStatusError
