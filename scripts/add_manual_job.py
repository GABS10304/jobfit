"""Add a single job found manually (pasted link, not from the sourcing
boards) into the same fit-check + state-store pipeline as the automated runs.

Fetches the page with a headless browser (works on JS-heavy career sites —
Oracle HCM/Taleo, Greenhouse, Lever, etc. — where a plain HTTP GET returns
an empty SPA shell), runs the existing V3 fit-check + sourcing filter, and
records it in out/tracking/jobs_state.json so it shows up like any other
proposed job ("ja zu <job_id>" works the same way afterwards).

Usage:
  python scripts/add_manual_job.py --url "https://.../job/24163" --company "Danske Bank"
  python scripts/add_manual_job.py --url "..." --jd-text-file /tmp/jd.txt --company "..."
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend import data_loader, fit_engine  # noqa: E402
from backend.sourcing.filtering import (  # noqa: E402
    evaluate_default_filter,
    evaluate_location_fit,
    evaluate_title_prefilter,
    evaluate_watchlist,
    relocation_note,
    top_fit_score,
)
from backend.sourcing.language_detect import detect_jd_language  # noqa: E402
from backend.sourcing.salary_filter import passes_salary_gate  # noqa: E402
from backend.tracking import state_store  # noqa: E402


def fetch_page_text(url: str) -> str:
    """Generic headless-browser text extraction — works on JS-rendered SPAs."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1500)
            return page.inner_text("body")
        finally:
            browser.close()


def add_manual_job(
    *,
    url: str,
    title: str | None,
    company: str | None,
    jd_text: str,
    state_path: Path | None = None,
) -> dict:
    role_fit_profile = data_loader.load_role_fit_profile()
    constraints = data_loader.load_constraints()

    fit = fit_engine.run_fit_check(
        job_description=jd_text, profile=role_fit_profile, constraints=constraints
    )
    top_score, top_role = top_fit_score(fit)
    resolved_title = title or _guess_title(jd_text)

    title_ok, title_reason = evaluate_title_prefilter(resolved_title)
    passes, reject_reason = evaluate_default_filter(
        fit.status_flag, top_score=top_score, top_role_id=top_role, title=resolved_title
    )
    watchlist_ok, watchlist_reason = evaluate_watchlist(
        fit.status_flag, top_score=top_score, top_role_id=top_role, title=resolved_title
    )
    min_annual_base = (
        constraints.compensation.min_annual_base if constraints.compensation else None
    )
    if not passes_salary_gate(jd_text, min_annual_base):
        passes = False
        watchlist_ok = False
        reject_reason = f"salary_below_minimum:min={min_annual_base}"

    location = evaluate_location_fit(jd_text, constraints.location_preferences)

    if not title_ok:
        bucket = "rejected"
    elif passes:
        bucket = "passed"
    elif watchlist_ok:
        bucket = "watchlist"
    else:
        bucket = "rejected"

    row = {
        "url": url,
        "title": resolved_title,
        "board_id": company or "manual",
        "fit_check": {
            "status_flag": fit.status_flag,
            "top_score": top_score,
            "location_match": location["match"],
        },
    }
    run_date = datetime.now(timezone.utc).strftime("%Y%m%d")
    new_rows = state_store.upsert_and_diff(
        [row],
        source_artifact="manual",
        run_date=run_date,
        sourcing_bucket=bucket,
        path=state_path,
    )

    job_id = state_store.make_job_id(url=url, title=resolved_title)
    return {
        "job_id": job_id,
        "title": resolved_title,
        "company": company,
        "bucket": bucket,
        "top_score": top_score,
        "top_role": top_role,
        "status_flag": fit.status_flag,
        "title_prefilter_reason": title_reason,
        "reject_reason": reject_reason,
        "language": detect_jd_language(jd_text),
        "location_match": location["match"],
        "relocation_note": relocation_note(top_score, location["match"]),
        "is_new": bool(new_rows),
    }


def _guess_title(jd_text: str) -> str:
    for line in jd_text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return "Unknown Title"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--title", default=None)
    parser.add_argument("--company", default=None)
    parser.add_argument(
        "--jd-text-file", type=Path, default=None, help="Skip fetching; read JD text from a file."
    )
    args = parser.parse_args()

    jd_text = (
        args.jd_text_file.read_text(encoding="utf-8")
        if args.jd_text_file
        else fetch_page_text(args.url)
    )

    result = add_manual_job(url=args.url, title=args.title, company=args.company, jd_text=jd_text)

    print(f"job_id: {result['job_id']}")
    print(f"title: {result['title']}")
    print(f"bucket: {result['bucket']} (status_flag={result['status_flag']})")
    print(f"top_score: {result['top_score']} ({result['top_role']})")
    print(f"language: {result['language']}")
    print(f"new: {result['is_new']}")
    if result["relocation_note"]:
        print(f"📍 {result['relocation_note']}")
    if result["bucket"] == "rejected":
        print(f"reject_reason: {result['title_prefilter_reason'] or result['reject_reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
