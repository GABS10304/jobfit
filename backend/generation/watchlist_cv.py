"""Generate labeled weak-match CV variants from sourcing watchlist rows.

Uses existing selection_plan + generate_cv_variant. Does not lower the
strong-match bar (min_top_score=75) and does not change V3 fit-engine logic.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from backend import data_loader, fit_engine
from backend.generation.cv_pdf import generate_cv_variant_pdf
from backend.generation.cv_variant import (
    generate_cv_variant,
    generate_cv_variant_plain,
)
from backend.generation.selection_plan import selection_plan
from backend.models import FitCheckResponse
from backend.sourcing.filtering import fit_check_jd_text
from backend.sourcing.personio import NormalizedJobDescription

WEAK_MATCH_LABEL = "weak-match"
PASSED_MATCH_LABEL = "passed"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def jd_text_from_job_dict(job: dict[str, Any]) -> str:
    """Rebuild fit-check JD text from a NormalizedJobDescription.to_dict() payload."""
    normalized = NormalizedJobDescription(
        title=str(job.get("title") or ""),
        location=job.get("location"),
        work_mode=job.get("work_mode"),
        employment_type=job.get("employment_type"),
        jd_text=str(job.get("jd_text") or ""),
        url=str(job.get("url") or ""),
        source=job.get("source") or "personio",
        fetched_at=str(job.get("fetched_at") or ""),
    )
    return fit_check_jd_text(normalized)


def slugify_title(title: str | None, *, max_len: int = 48) -> str:
    raw = (title or "untitled").casefold().strip()
    slug = _SLUG_RE.sub("-", raw).strip("-")
    if not slug:
        slug = "untitled"
    return slug[:max_len].rstrip("-")


_JOB_ID_URL_PATTERNS = (
    re.compile(r"/job/(\d+)"),  # Personio, Workday
    re.compile(r"/jobs/view/(?:[^/]*-)?(\d+)"),  # LinkedIn
    re.compile(r"^/companies/[^/]+/(\d+)(?:-|/?$)"),  # JOIN
)


def job_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    path = urlparse(url).path or ""
    for pattern in _JOB_ID_URL_PATTERNS:
        match = pattern.search(path)
        if match:
            return match.group(1)
    return None


def watchlist_cv_filename(
    *,
    title: str | None,
    url: str | None = None,
    top_score: int | None = None,
) -> str:
    """Filename clearly labeled as weak-match (not strong pass)."""
    parts = [WEAK_MATCH_LABEL]
    if top_score is not None:
        parts.append(f"score{int(top_score)}")
    job_id = job_id_from_url(url)
    if job_id:
        parts.append(job_id)
    parts.append(slugify_title(title))
    return "_".join(parts) + ".md"


def prepend_weak_match_note(
    markdown: str,
    *,
    title: str | None = None,
    top_score: int | None = None,
    watchlist_reason: str | None = None,
) -> str:
    """Insert a visible watchlist / weak-match banner above the CV body."""
    score_text = "n/a" if top_score is None else str(top_score)
    reason = watchlist_reason or f"weak_score={score_text}<75"
    title_line = f" | Rolle: {title}" if title else ""
    banner = (
        f"> **Weak-Match / Watchlist**{title_line} — "
        f"Score {score_text} unter Strong-Match-Bar (75). "
        f"Kein Strong-Pass; nur manuelle Prüfung. ({reason})\n"
        f"> Label: `{WEAK_MATCH_LABEL}`\n"
    )
    body = markdown.lstrip("\n")
    return banner + "\n" + body


def render_watchlist_cv(
    *,
    jd_text: str,
    fit: FitCheckResponse | None = None,
    title: str | None = None,
    top_score: int | None = None,
    watchlist_reason: str | None = None,
) -> str:
    """selection_plan + generate_cv_variant with weak-match header note.

    If ``fit`` is omitted, re-runs V3 fit-check on ``jd_text`` (deterministic).
    """
    cv = data_loader.load_cv_master()
    profile = data_loader.load_role_fit_profile()
    rules = data_loader.load_cv_rules()

    if fit is None:
        constraints = data_loader.load_constraints()
        fit = fit_engine.run_fit_check(
            job_description=jd_text,
            profile=profile,
            constraints=constraints,
        )

    plan = selection_plan(cv, profile, fit, jd_text, rules)
    rendered = generate_cv_variant(plan, cv, rules)
    return prepend_weak_match_note(
        rendered,
        title=title,
        top_score=top_score,
        watchlist_reason=watchlist_reason,
    )


def write_watchlist_cv_from_row(
    row: dict[str, Any],
    out_dir: Path,
    *,
    fit: FitCheckResponse | None = None,
) -> Path:
    """Render and write one watchlist row (.md + .pdf); returns .md path."""
    job = row.get("job") or {}
    if not isinstance(job, dict) or not job.get("jd_text"):
        raise ValueError(f"watchlist row missing job.jd_text: {row.get('url')}")

    fit_payload = row.get("fit_check") or {}
    top_score = fit_payload.get("top_score")
    if top_score is None and fit is not None:
        candidates = fit.results or fit.excluded_roles
        if candidates:
            top_score = max(candidates, key=lambda role: role.score).score

    reason = fit_payload.get("watchlist_reason") or row.get("reject_reason")
    title = row.get("title") or job.get("title")
    url = row.get("url") or job.get("url")

    jd_text = jd_text_from_job_dict(job)
    markdown = render_watchlist_cv(
        jd_text=jd_text,
        fit=fit,
        title=title,
        top_score=top_score if top_score is None else int(top_score),
        watchlist_reason=str(reason) if reason else None,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / watchlist_cv_filename(
        title=title,
        url=url,
        top_score=top_score if top_score is None else int(top_score),
    )
    path.write_text(markdown, encoding="utf-8")
    generate_cv_variant_pdf(markdown, path.with_suffix(".pdf"))
    return path


def write_watchlist_cvs(
    rows: list[dict[str, Any]],
    out_dir: Path,
    *,
    fits: dict[str, FitCheckResponse] | None = None,
) -> list[Path]:
    """Write CV markdown (+ .pdf sibling) for each watchlist row. ``fits`` keyed by job URL."""
    written: list[Path] = []
    fit_map = fits or {}
    for row in rows:
        url = str(row.get("url") or (row.get("job") or {}).get("url") or "")
        path = write_watchlist_cv_from_row(row, out_dir, fit=fit_map.get(url))
        written.append(path)
    return written


def passed_cv_filename(
    *,
    title: str | None,
    url: str | None = None,
    top_score: int | None = None,
) -> str:
    """Filename labeled as strong pass (score ≥ 75)."""
    parts = [PASSED_MATCH_LABEL]
    if top_score is not None:
        parts.append(f"score{int(top_score)}")
    job_id = job_id_from_url(url)
    if job_id:
        parts.append(job_id)
    parts.append(slugify_title(title))
    return "_".join(parts) + ".md"


def prepend_passed_note(
    markdown: str,
    *,
    title: str | None = None,
    top_score: int | None = None,
) -> str:
    """Insert a visible strong-pass banner above the CV body."""
    score_text = "n/a" if top_score is None else str(top_score)
    title_line = f" | Rolle: {title}" if title else ""
    banner = (
        f"> **Strong-Pass**{title_line} — "
        f"Score {score_text} ≥ Strong-Match-Bar (75). "
        f"Für Review / Bewerbung vorgesehen.\n"
        f"> Label: `{PASSED_MATCH_LABEL}`\n"
    )
    body = markdown.lstrip("\n")
    return banner + "\n" + body


def prepend_passed_note_plain(
    text: str,
    *,
    title: str | None = None,
    top_score: int | None = None,
) -> str:
    """Plain-text strong-pass banner (no markdown) for ATS paste siblings."""
    score_text = "n/a" if top_score is None else str(top_score)
    title_line = f" | Rolle: {title}" if title else ""
    banner = (
        f"Strong-Pass{title_line} — "
        f"Score {score_text} ≥ Strong-Match-Bar (75). "
        f"Für Review / Bewerbung vorgesehen.\n"
        f"Label: {PASSED_MATCH_LABEL}\n"
    )
    body = text.lstrip("\n")
    return banner + "\n" + body


def _passed_plan_and_bodies(
    *,
    jd_text: str,
    fit: FitCheckResponse | None = None,
) -> tuple[str, str]:
    """Return (markdown_body, plain_body) from selection_plan."""
    cv = data_loader.load_cv_master()
    profile = data_loader.load_role_fit_profile()
    rules = data_loader.load_cv_rules()

    if fit is None:
        constraints = data_loader.load_constraints()
        fit = fit_engine.run_fit_check(
            job_description=jd_text,
            profile=profile,
            constraints=constraints,
        )

    plan = selection_plan(cv, profile, fit, jd_text, rules)
    return (
        generate_cv_variant(plan, cv, rules),
        generate_cv_variant_plain(plan, cv, rules),
    )


def render_passed_cv(
    *,
    jd_text: str,
    fit: FitCheckResponse | None = None,
    title: str | None = None,
    top_score: int | None = None,
) -> str:
    """selection_plan + generate_cv_variant with strong-pass header note."""
    rendered, _plain = _passed_plan_and_bodies(jd_text=jd_text, fit=fit)
    return prepend_passed_note(
        rendered,
        title=title,
        top_score=top_score,
    )


def render_passed_cv_plain(
    *,
    jd_text: str,
    fit: FitCheckResponse | None = None,
    title: str | None = None,
    top_score: int | None = None,
) -> str:
    """selection_plan + generate_cv_variant_plain with plain strong-pass note."""
    _md, rendered = _passed_plan_and_bodies(jd_text=jd_text, fit=fit)
    return prepend_passed_note_plain(
        rendered,
        title=title,
        top_score=top_score,
    )


def write_passed_cv_from_row(
    row: dict[str, Any],
    out_dir: Path,
    *,
    fit: FitCheckResponse | None = None,
) -> Path:
    """Render and write one passed row (.md + .txt + .pdf); returns .md path."""
    job = row.get("job") or {}
    if not isinstance(job, dict) or not job.get("jd_text"):
        raise ValueError(f"passed row missing job.jd_text: {row.get('url')}")

    fit_payload = row.get("fit_check") or {}
    top_score = fit_payload.get("top_score")
    if top_score is None and fit is not None:
        candidates = fit.results or fit.excluded_roles
        if candidates:
            top_score = max(candidates, key=lambda role: role.score).score

    title = row.get("title") or job.get("title")
    url = row.get("url") or job.get("url")
    score = top_score if top_score is None else int(top_score)

    jd_text = jd_text_from_job_dict(job)
    md_body, plain_body = _passed_plan_and_bodies(jd_text=jd_text, fit=fit)
    markdown = prepend_passed_note(md_body, title=title, top_score=score)
    plain = prepend_passed_note_plain(plain_body, title=title, top_score=score)

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / passed_cv_filename(
        title=title,
        url=url,
        top_score=score,
    )
    path.write_text(markdown, encoding="utf-8")
    path.with_suffix(".txt").write_text(plain, encoding="utf-8")
    generate_cv_variant_pdf(plain, path.with_suffix(".pdf"))
    return path


def write_passed_cvs(
    rows: list[dict[str, Any]],
    out_dir: Path,
    *,
    fits: dict[str, FitCheckResponse] | None = None,
) -> list[Path]:
    """Write CV markdown (+ .txt + .pdf siblings) for each strong-pass row."""
    written: list[Path] = []
    fit_map = fits or {}
    for row in rows:
        url = str(row.get("url") or (row.get("job") or {}).get("url") or "")
        path = write_passed_cv_from_row(row, out_dir, fit=fit_map.get(url))
        written.append(path)
    return written
