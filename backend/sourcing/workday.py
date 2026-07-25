"""Fetch and parse Workday job posting pages into normalized JD JSON.

Board discovery uses the public CXS careers search API:
  POST https://{tenant}.wdN.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from backend.sourcing.personio import JobListing, NormalizedJobDescription

WORKDAY_HOST_MARKERS = ("myworkdayjobs.com", "myworkday.com")
DEFAULT_TIMEOUT = 30.0
CXS_PAGE_SIZE = 20  # Workday CXS hard cap per request
LOCALE_PATH_RE = re.compile(r"^[a-z]{2}-[a-z]{2}$", re.IGNORECASE)
TENANT_HOST_RE = re.compile(
    r"^(?P<tenant>[^.]+)\.wd\d+\.myworkdayjobs\.com$",
    re.IGNORECASE,
)


class _TextExtractor(HTMLParser):
    """Collect visible text from HTML, preserving block breaks."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._block_tags = frozenset(
            {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "ul", "ol"}
        )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._block_tags:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "div", "li", "h1", "h2", "h3", "h4"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self._parts.append(text)

    def get_text(self) -> str:
        raw = " ".join(self._parts)
        raw = re.sub(r"[ \t]+\n", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        raw = re.sub(r"[ \t]{2,}", " ", raw)
        return raw.strip()


def is_workday_job_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    path = parsed.path or ""
    if not any(marker in host for marker in WORKDAY_HOST_MARKERS):
        return False
    return "/job/" in path


def is_workday_board_url(url: str) -> bool:
    """True for Workday careers site roots (listing), not individual /job/ URLs."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    path = (parsed.path or "").rstrip("/")
    if "myworkdayjobs.com" not in host:
        return False
    if "/job/" in (parsed.path or ""):
        return False
    if "/wday/" in (parsed.path or "").casefold():
        return False
    parts = [p for p in path.split("/") if p]
    return bool(parts)


@dataclass(frozen=True)
class WorkdayBoardRef:
    """Parsed Workday careers board coordinates for CXS + public URLs."""

    origin: str
    tenant: str
    site: str
    locale: str | None
    board_url: str

    @property
    def cxs_jobs_url(self) -> str:
        return f"{self.origin}/wday/cxs/{self.tenant}/{self.site}/jobs"

    def job_url(self, external_path: str) -> str:
        path = external_path if external_path.startswith("/") else f"/{external_path}"
        if not path.startswith("/job/"):
            raise ValueError(f"Not a Workday externalPath job path: {external_path}")
        if self.locale:
            return f"{self.origin}/{self.locale}/{self.site}{path}"
        return f"{self.origin}/{self.site}{path}"


def parse_workday_board_url(url: str) -> WorkdayBoardRef:
    """Extract tenant/site/locale from a myworkdayjobs.com careers URL."""
    if not is_workday_board_url(url):
        raise ValueError(f"Not a Workday board URL: {url}")

    parsed = urlparse(url)
    host = parsed.hostname or ""
    match = TENANT_HOST_RE.match(host)
    if not match:
        raise ValueError(
            f"Unsupported Workday host (expected {{tenant}}.wdN.myworkdayjobs.com): {host}"
        )
    tenant = match.group("tenant")

    parts = [p for p in (parsed.path or "").split("/") if p]
    locale: str | None = None
    if len(parts) >= 2 and LOCALE_PATH_RE.match(parts[0]):
        locale = parts[0]
        site = parts[1]
    elif parts:
        site = parts[0]
    else:
        raise ValueError(f"Workday board URL missing site path: {url}")

    origin = f"{parsed.scheme}://{parsed.netloc}"
    if locale:
        board_path = f"/{locale}/{site}"
    else:
        board_path = f"/{site}"
    board_url = urlunparse(parsed._replace(path=board_path, params="", query="", fragment=""))
    return WorkdayBoardRef(
        origin=origin,
        tenant=tenant,
        site=site,
        locale=locale,
        board_url=board_url,
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(unescape(html))
    return parser.get_text()


def _first_match(pattern: str, html: str, flags: int = 0) -> str | None:
    match = re.search(pattern, html, flags)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _meta_content(html: str, prop: str) -> str | None:
    pattern = (
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+'
        rf'content=["\']([^"\']*)["\']'
        rf'|<meta[^>]+content=["\']([^"\']*)["\'][^>]+'
        rf'(?:property|name)=["\']{re.escape(prop)}["\']'
    )
    match = re.search(pattern, html, flags=re.IGNORECASE)
    if not match:
        return None
    value = (match.group(1) or match.group(2) or "").strip()
    return unescape(value) or None


def _extract_json_ld(html: str) -> dict[str, Any] | None:
    for block in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        try:
            payload = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and item.get("@type") == "JobPosting":
                    return item
            continue
        if isinstance(payload, dict) and payload.get("@type") == "JobPosting":
            return payload
    return None


def _location_from_json_ld(data: dict[str, Any]) -> str | None:
    locations = data.get("jobLocation")
    if locations is None:
        return None
    items = locations if isinstance(locations, list) else [locations]
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        address = item.get("address")
        if isinstance(address, str) and address.strip():
            parts.append(address.strip())
            continue
        if not isinstance(address, dict):
            continue
        locality = address.get("addressLocality")
        region = address.get("addressRegion")
        country = address.get("addressCountry")
        if locality and region and locality != region:
            parts.append(f"{locality}, {region}")
        elif locality:
            parts.append(str(locality))
        elif region:
            parts.append(str(region))
        elif country:
            parts.append(str(country))
    if not parts:
        return None
    seen: set[str] = set()
    unique: list[str] = []
    for part in parts:
        if part not in seen:
            seen.add(part)
            unique.append(part)
    return " / ".join(unique)


def _employment_type_from_json_ld(data: dict[str, Any]) -> str | None:
    raw = data.get("employmentType")
    values: list[str]
    if isinstance(raw, list):
        values = [str(v).strip() for v in raw if str(v).strip()]
    elif isinstance(raw, str) and raw.strip():
        values = [raw.strip()]
    else:
        return None
    mapped: list[str] = []
    for value in values:
        key = value.replace(" ", "").replace("_", "").casefold()
        if key in {"other", "unknown"}:
            continue
        if key in {"fulltime", "full-time"}:
            mapped.append("Full time")
        elif key in {"parttime", "part-time"}:
            mapped.append("Part time")
        elif key in {"contractor", "temporary", "intern", "volunteer", "perdiem"}:
            mapped.append(value)
        else:
            mapped.append(value)
    return ", ".join(mapped) if mapped else None


def _infer_work_mode(location: str | None, jd_text: str) -> str | None:
    haystack = " ".join(filter(None, [location, jd_text])).casefold()
    if re.search(r"\bhybrid|\bhybrides?\b", haystack):
        return "Hybrid"
    if re.search(r"\b(remote|home\s*office|work\s*from\s*home|mobil\s*arbeiten)\b", haystack):
        return "Remote"
    if re.search(r"\b(on[-\s]?site|office[-\s]?first|vor\s*ort)\b", haystack):
        return "On-site"
    return None


def _parse_from_json_ld(
    data: dict[str, Any], url: str, fetched_at: str
) -> NormalizedJobDescription | None:
    title = str(data.get("title") or "").strip()
    description_raw = str(data.get("description") or "").strip()
    if not title or not description_raw:
        return None
    jd_text = _html_to_text(description_raw)
    if not jd_text:
        return None
    location = _location_from_json_ld(data)
    employment_type = _employment_type_from_json_ld(data)
    work_mode = _infer_work_mode(location=location, jd_text=jd_text)
    return NormalizedJobDescription(
        title=title,
        location=location,
        work_mode=work_mode,
        employment_type=employment_type,
        jd_text=jd_text,
        url=url,
        source="workday",
        fetched_at=fetched_at,
    )


def _parse_from_dom(html: str, url: str, fetched_at: str) -> NormalizedJobDescription | None:
    """Fallback for SPA shells: OpenGraph / automation-id markup."""
    title = _meta_content(html, "og:title")
    if not title:
        title = _first_match(
            r'data-automation-id=["\']jobPostingHeader["\'][^>]*>.*?<h1[^>]*>(.*?)</h1>',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if title:
            title = _html_to_text(title)
    if not title:
        title = _first_match(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        if title:
            title = _html_to_text(title)

    location = _first_match(
        r'data-automation-id=["\']locations["\'][^>]*>(.*?)</(?:div|dd|span)>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if location:
        location = _html_to_text(location) or None

    employment_type = _first_match(
        r'data-automation-id=["\']time["\'][^>]*>(.*?)</(?:div|dd|span)>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if employment_type:
        employment_type = _html_to_text(employment_type) or None

    description_html = _first_match(
        r'data-automation-id=["\']jobPostingDescription["\'][^>]*>(.*?)</div>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if description_html:
        jd_text = _html_to_text(description_html)
    else:
        og_desc = _meta_content(html, "og:description")
        jd_text = og_desc.strip() if og_desc else ""

    if not title or not jd_text:
        return None

    work_mode = _infer_work_mode(location=location, jd_text=jd_text)
    return NormalizedJobDescription(
        title=title,
        location=location,
        work_mode=work_mode,
        employment_type=employment_type,
        jd_text=jd_text,
        url=url,
        source="workday",
        fetched_at=fetched_at,
    )


def parse_workday_html(
    html: str, url: str, fetched_at: str | None = None
) -> NormalizedJobDescription:
    """Parse Workday HTML using JSON-LD, then DOM / OpenGraph selectors."""
    ts = fetched_at or _utc_now_iso()
    json_ld = _extract_json_ld(html)
    if json_ld:
        parsed = _parse_from_json_ld(json_ld, url, ts)
        if parsed:
            dom = _parse_from_dom(html, url, ts)
            if dom:
                location = parsed.location or dom.location
                work_mode = parsed.work_mode or dom.work_mode
                employment_type = parsed.employment_type or dom.employment_type
                # Prefer longer JD body (JSON-LD usually has full text; OG may be truncated).
                jd_text = (
                    parsed.jd_text
                    if len(parsed.jd_text) >= len(dom.jd_text)
                    else dom.jd_text
                )
                return NormalizedJobDescription(
                    title=parsed.title or dom.title,
                    location=location,
                    work_mode=work_mode,
                    employment_type=employment_type,
                    jd_text=jd_text,
                    url=url,
                    source="workday",
                    fetched_at=ts,
                )
            return parsed

    dom = _parse_from_dom(html, url, ts)
    if dom:
        return dom
    raise ValueError("Could not parse Workday job page (JSON-LD and DOM strategies failed)")


def fetch_page_html(url: str, *, timeout: float = DEFAULT_TIMEOUT) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; job-fit-system/1.0; +https://github.com/local/job-fit-system)"
        ),
        "Accept": "text/html,application/xhtml+xml",
    }
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def _fetch_with_playwright(url: str, *, timeout_ms: int = 30000) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_selector(
                "script[type='application/ld+json'], "
                "[data-automation-id='jobPostingDescription'], "
                "[data-automation-id='jobPostingHeader']",
                timeout=timeout_ms,
            )
            return page.content()
        finally:
            browser.close()


def fetch_workday_job(url: str, *, use_playwright: bool = False) -> NormalizedJobDescription:
    """Fetch a Workday job URL and return normalized JD data."""
    if not is_workday_job_url(url):
        raise ValueError(f"Not a Workday job URL: {url}")

    fetched_at = _utc_now_iso()
    if use_playwright:
        html = _fetch_with_playwright(url)
        return parse_workday_html(html, url, fetched_at)

    html = fetch_page_html(url)
    try:
        return parse_workday_html(html, url, fetched_at)
    except ValueError:
        html = _fetch_with_playwright(url)
        return parse_workday_html(html, url, fetched_at)


def fetch_cxs_jobs(
    board: WorkdayBoardRef,
    *,
    offset: int = 0,
    limit: int = CXS_PAGE_SIZE,
    search_text: str = "",
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """POST one CXS jobs search page; returns raw JSON payload."""
    page_limit = max(1, min(int(limit), CXS_PAGE_SIZE))
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (compatible; job-fit-system/1.0; +https://github.com/local/job-fit-system)"
        ),
        "Origin": board.origin,
        "Referer": board.board_url,
    }
    payload = {
        "appliedFacets": {},
        "limit": page_limit,
        "offset": max(0, int(offset)),
        "searchText": search_text or "",
    }
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        response = client.post(board.cxs_jobs_url, json=payload)
        response.raise_for_status()
        content_type = (response.headers.get("content-type") or "").casefold()
        body = response.text
        if "json" not in content_type and body.lstrip()[:1] in {"<", ""}:
            raise ValueError(
                "Workday CXS returned non-JSON (possible WAF/HTML challenge) "
                f"for {board.cxs_jobs_url}"
            )
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Workday CXS returned non-JSON (possible WAF/HTML challenge) "
                f"for {board.cxs_jobs_url}"
            ) from exc
    if not isinstance(data, dict):
        raise ValueError("Workday CXS response is not a JSON object")
    return data


def listings_from_cxs_payload(
    payload: dict[str, Any], board: WorkdayBoardRef
) -> list[JobListing]:
    """Map a CXS jobs JSON page to JobListing rows (URL + title)."""
    postings = payload.get("jobPostings")
    if not isinstance(postings, list):
        return []

    listings: list[JobListing] = []
    seen: set[str] = set()
    for item in postings:
        if not isinstance(item, dict):
            continue
        external_path = str(item.get("externalPath") or "").strip()
        if not external_path:
            continue
        try:
            url = board.job_url(external_path)
        except ValueError:
            continue
        if url in seen:
            continue
        seen.add(url)
        title_raw = str(item.get("title") or "").strip()
        title = unescape(title_raw) if title_raw else None
        locations_raw = str(item.get("locationsText") or "").strip()
        locations_text = unescape(locations_raw) if locations_raw else None
        listings.append(
            JobListing(url=url, title=title, locations_text=locations_text)
        )
    return listings


CxsPageFetcher = Callable[..., dict[str, Any]]


def discover_job_listings(
    board_url: str,
    *,
    max_results: int | None = None,
    page_size: int = CXS_PAGE_SIZE,
    search_text: str = "",
    fetch_page: CxsPageFetcher | None = None,
) -> list[JobListing]:
    """Discover job listings (URL + title) via Workday CXS search pagination.

    ``fetch_page`` is injectable for offline tests:
      fetch_page(board, offset=..., limit=..., search_text=...) -> dict
    """
    board = parse_workday_board_url(board_url)
    fetcher: CxsPageFetcher = fetch_page or (
        lambda b, *, offset, limit, search_text: fetch_cxs_jobs(
            b, offset=offset, limit=limit, search_text=search_text
        )
    )

    listings: list[JobListing] = []
    seen: set[str] = set()
    offset = 0
    total: int | None = None
    page_limit = max(1, min(int(page_size), CXS_PAGE_SIZE))

    while True:
        if max_results is not None and len(listings) >= max_results:
            break
        payload = fetcher(
            board, offset=offset, limit=page_limit, search_text=search_text
        )
        if total is None:
            raw_total = payload.get("total")
            total = int(raw_total) if isinstance(raw_total, int) else None

        page = listings_from_cxs_payload(payload, board)
        if not page:
            break

        for listing in page:
            if listing.url in seen:
                continue
            seen.add(listing.url)
            listings.append(listing)
            if max_results is not None and len(listings) >= max_results:
                break

        offset += page_limit
        if total is not None and offset >= total:
            break
        if len(page) < page_limit:
            break

    if max_results is not None:
        return listings[:max_results]
    return listings


def discover_job_urls(
    board_url: str,
    *,
    max_results: int | None = None,
    page_size: int = CXS_PAGE_SIZE,
    search_text: str = "",
    fetch_page: CxsPageFetcher | None = None,
) -> list[str]:
    """Discover job detail URLs from a Workday careers board (CXS)."""
    return [
        listing.url
        for listing in discover_job_listings(
            board_url,
            max_results=max_results,
            page_size=page_size,
            search_text=search_text,
            fetch_page=fetch_page,
        )
    ]
