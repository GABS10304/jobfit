"""Fetch multiple Personio jobs and optionally run V3 fit-check with default filter.

Usage:
  python scripts/fetch_jobs_batch.py --board-url https://flex-capital-management-gmbh.jobs.personio.de/
  python scripts/fetch_jobs_batch.py --urls-file urls.txt
  python scripts/fetch_jobs_batch.py --board-url <url> --limit 5 --out results.json

Filter contract: title prefilter before fit-check; then exclude no_go; require
min_top_score, product top role, no title deny keywords.
See domain/sourcing_filter.yaml.

--limit N applies AFTER title prefilter (N product-ish candidates, not first N board URLs).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend import data_loader, fit_engine
from backend.sourcing.filtering import (
    evaluate_default_filter,
    evaluate_title_prefilter,
    fit_check_jd_text,
    top_fit_score,
)
from backend.sourcing.personio import (
    JobListing,
    NormalizedJobDescription,
    discover_job_listings,
    fetch_job_title,
    fetch_personio_job,
)


def _load_urls_from_file(path: Path) -> list[JobListing]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [
        JobListing(url=line.strip(), title=None)
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def _run_fit_check(job: NormalizedJobDescription) -> dict[str, Any]:
    profile = data_loader.load_role_fit_profile()
    constraints = data_loader.load_constraints()
    fit = fit_engine.run_fit_check(
        job_description=fit_check_jd_text(job),
        profile=profile,
        constraints=constraints,
    )
    top_score, top_role = top_fit_score(fit)
    passes, reject_reason = evaluate_default_filter(
        fit.status_flag,
        top_score=top_score,
        top_role_id=top_role,
        title=job.title,
    )
    payload = {
        "status_flag": fit.status_flag,
        "verify_product_ownership": fit.verify_product_ownership,
        "presence_policy": fit.presence_policy.model_dump(),
        "top_score": top_score,
        "top_role_id": top_role,
        "passes_default_filter": passes,
    }
    if reject_reason:
        payload["filter_reject_reason"] = reject_reason
    return payload


def _resolve_listing_title(
    listing: JobListing, *, use_playwright: bool
) -> tuple[str | None, str | None]:
    """Return (title, error). Uses board title when present; else fetches title only."""
    if listing.title and listing.title.strip():
        return listing.title.strip(), None
    try:
        title = fetch_job_title(listing.url, use_playwright=use_playwright)
    except Exception as exc:
        return None, str(exc)
    return title, None


def _prefilter_listings(
    listings: list[JobListing],
    *,
    use_playwright: bool,
) -> tuple[list[JobListing], list[dict[str, Any]]]:
    """Split into prefilter-pass candidates and rejected rows (no fit-check)."""
    candidates: list[JobListing] = []
    rejected: list[dict[str, Any]] = []

    for listing in listings:
        title, fetch_error = _resolve_listing_title(listing, use_playwright=use_playwright)
        if fetch_error:
            rejected.append(
                {
                    "url": listing.url,
                    "status": "error",
                    "title": title,
                    "passes_default_filter": False,
                    "reject_reason": f"title_prefilter:fetch_error: {fetch_error}",
                }
            )
            continue

        passes, reason = evaluate_title_prefilter(title)
        if not passes:
            rejected.append(
                {
                    "url": listing.url,
                    "status": "rejected",
                    "title": title,
                    "passes_default_filter": False,
                    "reject_reason": reason or "title_prefilter",
                }
            )
            continue

        candidates.append(JobListing(url=listing.url, title=title))

    return candidates, rejected


def _process_job(
    url: str,
    *,
    use_playwright: bool,
    fit_check: bool,
    listing_title: str | None = None,
) -> dict[str, Any]:
    try:
        job = fetch_personio_job(url, use_playwright=use_playwright)
    except Exception as exc:
        return {
            "url": url,
            "status": "error",
            "title": listing_title,
            "error": str(exc),
            "passes_default_filter": False,
            "reject_reason": f"fetch_error: {exc}",
        }

    entry: dict[str, Any] = {
        "url": url,
        "status": "ok",
        "title": job.title,
        "job": job.to_dict(),
    }

    if fit_check:
        fit_payload = _run_fit_check(job)
        entry["fit_check"] = fit_payload
        entry["passes_default_filter"] = fit_payload["passes_default_filter"]
        if not fit_payload["passes_default_filter"]:
            detail = fit_payload.get("filter_reject_reason") or fit_payload["status_flag"]
            entry["reject_reason"] = f"filter: {detail}"
    else:
        entry["passes_default_filter"] = True

    return entry


def _print_summary_table(rows: list[dict[str, Any]]) -> None:
    headers = ("title", "status_flag", "top_score", "pass", "url")
    table_rows: list[tuple[str, str, str, str, str]] = []

    for row in rows:
        title = str(row.get("title") or (row.get("job") or {}).get("title") or "-")
        if row.get("status") == "error":
            table_rows.append((title, "error", "-", "FAIL", row["url"]))
            continue
        if row.get("reject_reason", "").startswith("title_prefilter"):
            table_rows.append((title, "prefilter", "-", "FAIL", row["url"]))
            continue

        job = row.get("job", {})
        fit = row.get("fit_check", {})
        title = str(job.get("title") or title or "-")
        status_flag = str(fit.get("status_flag") or "-")
        top_score = fit.get("top_score")
        top_score_text = str(top_score) if top_score is not None else "-"
        passed = "PASS" if row.get("passes_default_filter") else "FAIL"
        table_rows.append((title, status_flag, top_score_text, passed, row["url"]))

    widths = [len(header) for header in headers]
    for values in table_rows:
        for index, value in enumerate(values):
            widths[index] = max(widths[index], len(value))

    def _fmt(values: tuple[str, ...]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(values))

    print(_fmt(headers))
    print(_fmt(tuple("-" * width for width in widths)))
    for values in table_rows:
        print(_fmt(values))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch-fetch Personio jobs and apply default sourcing filter.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--board-url",
        help="Personio company careers board URL (*.jobs.personio.de/)",
    )
    source.add_argument(
        "--urls-file",
        type=Path,
        help="Text file with one Personio job URL per line",
    )
    parser.add_argument(
        "--fit-check",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run V3 fit-check and apply sourcing_filter (default: on)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("results.json"),
        help="Write JSON results to this path (default: results.json)",
    )
    parser.add_argument(
        "--playwright",
        action="store_true",
        help="Force Playwright for board discovery and job fetch",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process at most N jobs AFTER title prefilter",
    )
    args = parser.parse_args()

    board_url = args.board_url
    if args.board_url:
        listings = discover_job_listings(args.board_url, use_playwright=args.playwright)
    else:
        listings = _load_urls_from_file(args.urls_file)

    if not listings:
        print("No job URLs to process.", file=sys.stderr)
        return 1

    print(f"discovered {len(listings)} listing(s); running title prefilter...")
    candidates, prefilter_rejected = _prefilter_listings(
        listings, use_playwright=args.playwright
    )
    candidates_after_prefilter = len(candidates)
    print(
        f"prefilter: {candidates_after_prefilter} candidate(s), "
        f"{len(prefilter_rejected)} rejected"
    )

    limited = False
    to_process = candidates
    if args.limit is not None:
        limited = candidates_after_prefilter > args.limit
        to_process = candidates[: args.limit]
        print(f"limit={args.limit}: processing {len(to_process)} candidate(s)")

    if not to_process and not prefilter_rejected:
        print("No job URLs to process.", file=sys.stderr)
        return 1

    rows: list[dict[str, Any]] = list(prefilter_rejected)
    if to_process:
        print(f"fit-check on {len(to_process)} job(s)...")
        rows.extend(
            _process_job(
                listing.url,
                use_playwright=args.playwright,
                fit_check=args.fit_check,
                listing_title=listing.title,
            )
            for listing in to_process
        )

    passed = [row for row in rows if row.get("passes_default_filter")]
    rejected = [row for row in rows if not row.get("passes_default_filter")]

    _print_summary_table(rows)

    payload = {
        "board_url": board_url,
        "fit_check_enabled": args.fit_check,
        "discovered": len(listings),
        "prefilter_rejected_count": len(prefilter_rejected),
        "candidates_after_prefilter": candidates_after_prefilter,
        "fit_checked": len(to_process),
        "limit": args.limit,
        "limit_applied_after_prefilter": True,
        "limited": limited,
        "processed": len(rows),
        "passed_count": len(passed),
        "rejected_count": len(rejected),
        "passed": passed,
        "rejected": rejected,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwritten: {args.out}")
    print(f"passed: {len(passed)} | rejected: {len(rejected)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
