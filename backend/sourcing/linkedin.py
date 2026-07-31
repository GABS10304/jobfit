"""Search LinkedIn's public "jobs-guest" job board and fetch job detail pages.

No authentication, no API key. Same data source and HTML-regex parsing
approach as MadsLorentzen/ai-job-search's linkedin-search skill (MIT,
ported from TypeScript to Python here) — chosen because it's a proven,
working pattern rather than something reverse-engineered from scratch.

Personal-use only: automated access to these endpoints is against LinkedIn's
Terms of Service. Keep query volume low (this module is meant to run once
daily via a small, fixed list of searches, not to be polled or scaled up).
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urlencode

import httpx

from backend.sourcing.personio import JobListing, NormalizedJobDescription

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"

# A real browser UA + these headers are what LinkedIn's guest endpoints
# expect; job-fit-system's honest self-identifying UA (see personio.py)
# gets blocked here.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
}
_TIMEOUT = 15.0
_MAX_RETRIES = 6
_BASE_DELAY = 0.5
_MAX_DELAY = 8.0

_URN_SPLIT_RE = re.compile(r'data-entity-urn="urn:li:jobPosting:')
_ID_PREFIX_RE = re.compile(r"^(\d+)")
_FULL_LINK_RE = re.compile(r'class="base-card__full-link[^"]*"[^>]*href="([^"]+)"', re.I)
_TITLE_H3_RE = re.compile(r'class="base-search-card__title"[^>]*>([\s\S]*?)</h3>', re.I)
_TITLE_SR_RE = re.compile(r'class="sr-only"[^>]*>([\s\S]*?)</span>', re.I)
_SUBTITLE_RE = re.compile(r'class="base-search-card__subtitle"[^>]*>([\s\S]*?)</h4>', re.I)
_HREF_RE = re.compile(r'href="([^"]+)"', re.I)
_LOCATION_RE = re.compile(r'class="job-search-card__location"[^>]*>([\s\S]*?)</span>', re.I)

_DETAIL_TITLE_RE = re.compile(
    r'class="(?:top-card-layout__title|topcard__title)[^"]*"[^>]*>([\s\S]*?)</h[12]>', re.I
)
_DETAIL_ORG_RE = re.compile(
    r'class="topcard__org-name-link[^"]*"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', re.I
)
_DETAIL_LOCATION_RE = re.compile(
    r'class="topcard__flavor topcard__flavor--bullet"[^>]*>([\s\S]*?)</span>', re.I
)
_DETAIL_DESC_RE = re.compile(
    r'class="(?:show-more-less-html__markup|description__text)[^"]*"[^>]*>([\s\S]*?)'
    r'(?:<div class="show-more-less-html__button|</section>)',
    re.I,
)
_DETAIL_CRITERIA_RE = re.compile(
    r'class="description__job-criteria-subheader"[^>]*>([\s\S]*?)</h3>[\s\S]*?'
    r'class="description__job-criteria-text[^"]*"[^>]*>([\s\S]*?)</span>',
    re.I,
)
_BR_RE = re.compile(r"<\s*br\s*/?>", re.I)
_BLOCK_CLOSE_RE = re.compile(r"</(?:p|li|ul|ol|div|h\d)>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(html: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", html)).strip()


def _clean(html: str) -> str:
    return unescape(_strip_tags(html))


def _strip_tags_preserve_breaks(html_with_explicit_newlines: str) -> str:
    """Like _strip_tags, but keeps the \\n block breaks callers already
    inserted (e.g. for <br>/</p>) instead of collapsing them to spaces —
    matches Personio's jd_text paragraph formatting (see personio.py)."""
    text = _TAG_RE.sub(" ", html_with_explicit_newlines)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _html_fetch(url: str) -> str:
    """GET with exponential backoff on 429/5xx; empty string on 404."""
    delay = _BASE_DELAY
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=_TIMEOUT, follow_redirects=True, headers=_HEADERS) as client:
                response = client.get(url)
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt == _MAX_RETRIES:
                raise
            time.sleep(min(delay, _MAX_DELAY))
            delay *= 2
            continue
        if response.status_code == 404:
            return ""
        if response.status_code == 429 or response.status_code >= 500:
            if attempt == _MAX_RETRIES:
                raise httpx.HTTPStatusError(
                    f"Request failed: {response.status_code}",
                    request=response.request,
                    response=response,
                )
            time.sleep(min(delay, _MAX_DELAY))
            delay *= 2
            continue
        response.raise_for_status()
        return response.text
    if last_exc:
        raise last_exc
    raise RuntimeError("LinkedIn fetch failed after max retries")


def jobage_to_tpr(days: int | None) -> str | None:
    if not days or days <= 0 or days >= 9999:
        return None
    return f"r{days * 86400}"


def work_type_flag(mode: str | None) -> str | None:
    return {"remote": "2", "hybrid": "3", "onsite": "1", "on-site": "1"}.get(
        (mode or "").casefold()
    )


def job_id_from_linkedin_url(url: str) -> str | None:
    match = re.search(r"-(\d{6,})(?:\?|$)", url) or re.search(r"(\d{6,})", url)
    return match.group(1) if match else None


def parse_job_cards(html: str) -> list[JobListing]:
    listings: list[JobListing] = []
    for chunk in _URN_SPLIT_RE.split(html)[1:]:
        id_match = _ID_PREFIX_RE.match(chunk)
        if not id_match:
            continue
        job_id = id_match.group(1)

        link_match = _FULL_LINK_RE.search(chunk)
        url = unescape(link_match.group(1)).split("?")[0] if link_match else ""

        title = None
        h3 = _TITLE_H3_RE.search(chunk)
        if h3:
            title = _clean(h3.group(1))
        if not title:
            sr = _TITLE_SR_RE.search(chunk)
            if sr:
                title = _clean(sr.group(1))
        if not title:
            continue

        company = None
        sub = _SUBTITLE_RE.search(chunk)
        if sub:
            company = _clean(sub.group(1)) or None

        loc = _LOCATION_RE.search(chunk)
        location = _clean(loc.group(1)) if loc else None

        listings.append(
            JobListing(
                url=url or f"https://www.linkedin.com/jobs/view/{job_id}",
                title=title,
                locations_text=location,
                company=company,
            )
        )
    return listings


def search_jobs(
    *,
    query: str | None = None,
    location: str | None = None,
    jobage_days: int | None = None,
    remote: str | None = None,
    page: int = 1,
) -> list[JobListing]:
    """Search LinkedIn's public guest job board. 10 results per page."""
    params: dict[str, str] = {}
    if query:
        params["keywords"] = query
    if location:
        params["location"] = location
    tpr = jobage_to_tpr(jobage_days)
    if tpr:
        params["f_TPR"] = tpr
    wt = work_type_flag(remote)
    if wt:
        params["f_WT"] = wt
    params["start"] = str((page - 1) * 10)

    url = f"{SEARCH_URL}?{urlencode(params)}"
    html = _html_fetch(url)
    return parse_job_cards(html)


def parse_job_detail(html: str, job_id: str) -> tuple[NormalizedJobDescription, str | None]:
    """Parse a LinkedIn job detail page: (normalized JD, company name).

    Company isn't part of NormalizedJobDescription (Personio/Workday don't
    need it — one board is one company); LinkedIn spans many companies per
    search, so callers need it returned alongside.
    """
    title_match = _DETAIL_TITLE_RE.search(html)
    title = _clean(title_match.group(1)) if title_match else "(untitled)"

    org_match = _DETAIL_ORG_RE.search(html)
    company = _clean(org_match.group(2)) if org_match else None

    loc_match = _DETAIL_LOCATION_RE.search(html)
    location = _clean(loc_match.group(1)) if loc_match else None

    desc_match = _DETAIL_DESC_RE.search(html)
    jd_text = ""
    if desc_match:
        with_breaks = _BLOCK_CLOSE_RE.sub("\n", _BR_RE.sub("\n", desc_match.group(1)))
        jd_text = unescape(_strip_tags_preserve_breaks(with_breaks))

    criteria: dict[str, str] = {}
    for label_html, value_html in _DETAIL_CRITERIA_RE.findall(html):
        criteria[_clean(label_html).casefold()] = _clean(value_html)

    job = NormalizedJobDescription(
        title=title,
        location=location,
        work_mode=None,
        employment_type=criteria.get("employment type"),
        jd_text=jd_text,
        url=f"https://www.linkedin.com/jobs/view/{job_id}",
        source="linkedin",
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
    return job, company


def fetch_job_detail(url_or_id: str) -> tuple[NormalizedJobDescription, str | None]:
    """Fetch + parse a LinkedIn job's detail page: (normalized JD, company)."""
    job_id = url_or_id if url_or_id.isdigit() else job_id_from_linkedin_url(url_or_id)
    if not job_id:
        raise ValueError(f"Could not extract a LinkedIn job id from: {url_or_id!r}")

    html = _html_fetch(f"{DETAIL_URL}/{job_id}")
    if not html:
        raise ValueError(f"LinkedIn job not found (404): {job_id}")

    return parse_job_detail(html, job_id)
