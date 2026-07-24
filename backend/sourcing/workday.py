"""Fetch and parse Workday job posting pages into normalized JD JSON."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx

from backend.sourcing.personio import NormalizedJobDescription

WORKDAY_HOST_MARKERS = ("myworkdayjobs.com", "myworkday.com")
DEFAULT_TIMEOUT = 30.0


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
