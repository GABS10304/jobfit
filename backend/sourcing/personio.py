"""Fetch and parse Personio job posting pages into normalized JD JSON."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Any, Literal
from urllib.parse import urlparse, urlunparse

import httpx

PERSONIO_HOST_SUFFIX = ".jobs.personio."
DEFAULT_TIMEOUT = 30.0
JOB_ID_PATTERN = re.compile(r"/job/(\d+)(?:\?[^\s\"'<>]*)?", re.IGNORECASE)


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


@dataclass(frozen=True)
class NormalizedJobDescription:
    title: str
    location: str | None
    work_mode: str | None
    employment_type: str | None
    jd_text: str
    url: str
    source: Literal["personio"]
    fetched_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_personio_job_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    path = parsed.path or ""
    return PERSONIO_HOST_SUFFIX in host and "/job/" in path


def is_personio_board_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    path = parsed.path or ""
    return PERSONIO_HOST_SUFFIX in host and "/job/" not in path


def _board_origin(board_url: str) -> str:
    parsed = urlparse(board_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def normalize_board_url(url: str) -> str:
    if not is_personio_board_url(url):
        raise ValueError(f"Not a Personio board URL: {url}")
    parsed = urlparse(url)
    path = parsed.path or "/"
    if path != "/":
        path = "/"
    normalized = parsed._replace(path=path, fragment="")
    return urlunparse(normalized)


def _canonical_job_url(origin: str, job_id: str, query: str | None = None) -> str:
    path = f"/job/{job_id}"
    if query:
        return f"{origin}{path}?{query}"
    return f"{origin}{path}"


def extract_job_urls_from_html(html: str, board_url: str) -> list[str]:
    """Extract unique Personio job detail URLs from a careers listing page."""
    origin = _board_origin(board_url)
    seen: set[str] = set()
    urls: list[str] = []

    for match in JOB_ID_PATTERN.finditer(html):
        job_id = match.group(1)
        fragment = match.group(0)
        query = None
        if "?" in fragment:
            query = fragment.split("?", 1)[1]
            for stop in ('"', "'", "<", " ", "\\"):
                if stop in query:
                    query = query.split(stop, 1)[0]
        canonical = _canonical_job_url(origin, job_id, query)
        if canonical not in seen:
            seen.add(canonical)
            urls.append(canonical)

    return urls


def _fetch_board_with_playwright(board_url: str, *, timeout_ms: int = 30000) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(board_url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_selector("a[href*='/job/']", timeout=timeout_ms)
            return page.content()
        finally:
            browser.close()


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
        if isinstance(payload, dict) and payload.get("@type") == "JobPosting":
            return payload
    return None


def _location_from_json_ld(data: dict[str, Any]) -> str | None:
    locations = data.get("jobLocation")
    if not isinstance(locations, list):
        return None
    parts: list[str] = []
    for item in locations:
        if not isinstance(item, dict):
            continue
        address = item.get("address")
        if not isinstance(address, dict):
            continue
        locality = address.get("addressLocality")
        region = address.get("addressRegion")
        if locality and region and locality != region:
            parts.append(f"{locality}, {region}")
        elif locality:
            parts.append(str(locality))
    if not parts:
        return None
    # Preserve order but drop duplicates.
    seen: set[str] = set()
    unique: list[str] = []
    for part in parts:
        if part not in seen:
            seen.add(part)
            unique.append(part)
    return " / ".join(unique)


def _employment_type_from_json_ld(data: dict[str, Any]) -> str | None:
    raw = data.get("employmentType")
    if isinstance(raw, list):
        values = [str(v).strip() for v in raw if str(v).strip()]
        return ", ".join(values) if values else None
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _parse_from_json_ld(
    data: dict[str, Any], url: str, fetched_at: str
) -> NormalizedJobDescription | None:
    title = str(data.get("title") or "").strip()
    description_html = str(data.get("description") or "").strip()
    if not title or not description_html:
        return None
    jd_text = _html_to_text(description_html)
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
        source="personio",
        fetched_at=fetched_at,
    )


def _parse_from_dom(html: str, url: str, fetched_at: str) -> NormalizedJobDescription | None:
    title = _first_match(
        r'<h1[^>]*class="[^"]*job-position-title[^"]*"[^>]*>(.*?)</h1>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not title:
        title = _first_match(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        if title:
            title = re.sub(r"\s*\|\s*Jobs bei.*$", "", title, flags=re.IGNORECASE).strip()
    if title:
        title = _html_to_text(title)

    location = _first_match(
        r'class="[^"]*TruncatedLocations_locationText__[^"]*"[^>]*>(.*?)</span>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if location:
        location = _html_to_text(location)

    meta_items = re.findall(
        r'class="[^"]*JobAttributes_jobMetaText__[^"]*"[^>]*>(.*?)</span>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    employment_type: str | None = None
    schedule: str | None = None
    for item in meta_items:
        text = _html_to_text(item)
        if not text or text == location:
            continue
        lowered = text.casefold()
        if any(token in lowered for token in ("zeit", "time", "vollzeit", "teilzeit", "full-time")):
            schedule = text
        elif employment_type is None:
            employment_type = text
    if schedule and employment_type:
        employment_type = f"{schedule} · {employment_type}"
    elif schedule:
        employment_type = schedule

    description_blocks = re.findall(
        r'class="[^"]*page_jobDescriptionItem__[^"]*"[^>]*>.*?'
        r'class="[^"]*detail-block-title[^"]*"[^>]*>(.*?)</h2>.*?'
        r'class="[^"]*detail-block-description[^"]*"[^>]*>(.*?)</div>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    jd_parts: list[str] = []
    for heading, body in description_blocks:
        heading_text = _html_to_text(heading).rstrip(":")
        body_text = _html_to_text(body)
        if not body_text:
            continue
        if heading_text:
            jd_parts.append(f"{heading_text}\n{body_text}")
        else:
            jd_parts.append(body_text)
    jd_text = "\n\n".join(jd_parts).strip()

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
        source="personio",
        fetched_at=fetched_at,
    )


def _infer_work_mode(location: str | None, jd_text: str) -> str | None:
    haystack = " ".join(filter(None, [location, jd_text])).casefold()
    if re.search(r"\bhybrid\b", haystack):
        return "Hybrid"
    if re.search(r"\b(remote|home\s*office|work\s*from\s*home)\b", haystack):
        return "Remote"
    if re.search(r"\b(on[-\s]?site|office[-\s]?first|vor\s*ort)\b", haystack):
        return "On-site"
    return None


def parse_personio_html(html: str, url: str, fetched_at: str | None = None) -> NormalizedJobDescription:
    """Parse Personio HTML using JSON-LD, then DOM selectors."""
    ts = fetched_at or _utc_now_iso()
    json_ld = _extract_json_ld(html)
    if json_ld:
        parsed = _parse_from_json_ld(json_ld, url, ts)
        if parsed:
            dom = _parse_from_dom(html, url, ts)
            if dom:
                location = dom.location or parsed.location
                work_mode = dom.work_mode or parsed.work_mode
                employment_type = dom.employment_type or parsed.employment_type
                jd_text = dom.jd_text if len(dom.jd_text) >= len(parsed.jd_text) else parsed.jd_text
                return NormalizedJobDescription(
                    title=dom.title or parsed.title,
                    location=location,
                    work_mode=work_mode,
                    employment_type=employment_type,
                    jd_text=jd_text,
                    url=url,
                    source="personio",
                    fetched_at=ts,
                )
            return parsed

    dom = _parse_from_dom(html, url, ts)
    if dom:
        return dom
    raise ValueError("Could not parse Personio job page (JSON-LD and DOM strategies failed)")


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
                "main#main-content, h1.job-position-title, script[type='application/ld+json']",
                timeout=timeout_ms,
            )
            return page.content()
        finally:
            browser.close()


def discover_job_urls(company_board_url: str, *, use_playwright: bool = False) -> list[str]:
    """Discover job detail URLs from a Personio company careers board."""
    board_url = normalize_board_url(company_board_url)
    if use_playwright:
        html = _fetch_board_with_playwright(board_url)
        return extract_job_urls_from_html(html, board_url)

    html = fetch_page_html(board_url)
    urls = extract_job_urls_from_html(html, board_url)
    if urls:
        return urls

    html = _fetch_board_with_playwright(board_url)
    return extract_job_urls_from_html(html, board_url)


def fetch_personio_job(url: str, *, use_playwright: bool = False) -> NormalizedJobDescription:
    """Fetch a Personio job URL and return normalized JD data."""
    if not is_personio_job_url(url):
        raise ValueError(f"Not a Personio job URL: {url}")

    fetched_at = _utc_now_iso()
    html = fetch_page_html(url)
    try:
        return parse_personio_html(html, url, fetched_at)
    except ValueError:
        if not use_playwright:
            html = _fetch_with_playwright(url)
            return parse_personio_html(html, url, fetched_at)
        raise
