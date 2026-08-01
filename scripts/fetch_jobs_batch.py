"""Fetch multiple Personio jobs and optionally run V3 fit-check with default filter.

Usage:
  python scripts/fetch_jobs_batch.py --board-url https://flex-capital-management-gmbh.jobs.personio.de/
  python scripts/fetch_jobs_batch.py --urls-file urls.txt
  python scripts/fetch_jobs_batch.py --board-url <url> --limit 5 --out results.json
  python scripts/fetch_jobs_batch.py --board-url <url> --include-weak-proceed --out results.json
  python scripts/fetch_jobs_batch.py --board-url <url> --include-weak-proceed \\
      --cv-from-watchlist --cv-out out/cv_watchlist --limit 3

Filter contract: title prefilter before fit-check; then exclude no_go; require
min_top_score (75, strong match), product top role, no title deny keywords.
See domain/sourcing_filter.yaml.

--include-weak-proceed: also list proceed/verify product titles with score <75
as watchlist (not passed). Does not lower min_top_score.

--cv-from-watchlist: for each watchlist row, run selection_plan + generate_cv_variant
and write labeled weak-match markdown under --cv-out (default out/cv_watchlist).
Implies --include-weak-proceed. Strong passed stays separate (no auto CV here).

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
from backend.generation.watchlist_cv import write_passed_cvs, write_watchlist_cvs
from backend.models import FitCheckResponse
from backend.sourcing.filtering import (
    evaluate_default_filter,
    evaluate_location_fit,
    evaluate_title_prefilter,
    evaluate_watchlist,
    fit_check_jd_text,
    top_fit_score,
)
from backend.sourcing.salary_filter import passes_salary_gate
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


def _run_fit_check(
    job: NormalizedJobDescription,
) -> tuple[FitCheckResponse, dict[str, Any]]:
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
    watchlist_ok, watchlist_reason = evaluate_watchlist(
        fit.status_flag,
        top_score=top_score,
        top_role_id=top_role,
        title=job.title,
    )

    min_annual_base = (
        constraints.compensation.min_annual_base if constraints.compensation else None
    )
    if not passes_salary_gate(job.jd_text, min_annual_base):
        # Hard exclude: below the floor is below the floor, not "maybe worth it".
        passes = False
        watchlist_ok = False
        reject_reason = f"salary_below_minimum:min={min_annual_base}"

    location = evaluate_location_fit(job.jd_text, constraints.location_preferences)

    payload = {
        "status_flag": fit.status_flag,
        "verify_product_ownership": fit.verify_product_ownership,
        "presence_policy": fit.presence_policy.model_dump(),
        "top_score": top_score,
        "top_role_id": top_role,
        "passes_default_filter": passes,
        "watchlist_eligible": watchlist_ok and not passes,
        "location_match": location["match"],
    }
    if reject_reason:
        payload["filter_reject_reason"] = reject_reason
    if watchlist_ok and not passes and watchlist_reason:
        payload["watchlist_reason"] = watchlist_reason
    return fit, payload


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
        fit, fit_payload = _run_fit_check(job)
        entry["fit_check"] = fit_payload
        # In-memory only: reuse for --cv-from-watchlist; stripped before JSON write.
        entry["_fit"] = fit
        entry["passes_default_filter"] = fit_payload["passes_default_filter"]
        entry["watchlist"] = bool(fit_payload.get("watchlist_eligible"))
        if fit_payload["passes_default_filter"]:
            entry["sourcing_bucket"] = "passed"
        elif entry["watchlist"]:
            entry["sourcing_bucket"] = "watchlist"
            detail = fit_payload.get("watchlist_reason") or fit_payload.get(
                "filter_reject_reason"
            )
            entry["reject_reason"] = f"watchlist: {detail}"
        else:
            entry["sourcing_bucket"] = "rejected"
            detail = fit_payload.get("filter_reject_reason") or fit_payload["status_flag"]
            entry["reject_reason"] = f"filter: {detail}"
    else:
        entry["passes_default_filter"] = True
        entry["watchlist"] = False
        entry["sourcing_bucket"] = "passed"

    return entry


def _strip_private_fields(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop non-JSON helpers (e.g. cached FitCheckResponse) before serialize."""
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        cleaned.append({key: value for key, value in row.items() if not key.startswith("_")})
    return cleaned


def _print_summary_table(rows: list[dict[str, Any]], *, show_watchlist: bool) -> None:
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
        if row.get("passes_default_filter"):
            outcome = "PASS"
        elif show_watchlist and row.get("watchlist"):
            outcome = "WATCH"
        else:
            outcome = "FAIL"
        table_rows.append((title, status_flag, top_score_text, outcome, row["url"]))

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
    parser.add_argument(
        "--include-weak-proceed",
        action="store_true",
        help=(
            "Also list proceed/verify product titles with score < min_top_score "
            "as watchlist (not passed). Does not lower the strong-match bar."
        ),
    )
    parser.add_argument(
        "--cv-from-watchlist",
        action="store_true",
        help=(
            "For each watchlist item, run selection_plan + CV render and write "
            "labeled weak-match markdown under --cv-out. Implies "
            "--include-weak-proceed. Does not write CVs for strong passed."
        ),
    )
    parser.add_argument(
        "--cv-from-passed",
        action="store_true",
        help=(
            "For each strong-pass item, run selection_plan + CV render and write "
            "labeled passed markdown under --cv-out-passed."
        ),
    )
    parser.add_argument(
        "--cv-out",
        type=Path,
        default=Path("out/cv_watchlist"),
        help="Directory for watchlist CV markdown (default: out/cv_watchlist)",
    )
    parser.add_argument(
        "--cv-out-passed",
        type=Path,
        default=Path("out/cv_passed"),
        help="Directory for passed CV markdown (default: out/cv_passed)",
    )
    args = parser.parse_args()

    if args.cv_from_watchlist:
        args.include_weak_proceed = True

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
    watchlist = [
        row
        for row in rows
        if args.include_weak_proceed
        and row.get("watchlist")
        and not row.get("passes_default_filter")
    ]
    watchlist_urls = {row["url"] for row in watchlist}
    rejected = [
        row
        for row in rows
        if not row.get("passes_default_filter") and row["url"] not in watchlist_urls
    ]

    _print_summary_table(rows, show_watchlist=args.include_weak_proceed)

    cv_paths: list[str] = []
    if args.cv_from_watchlist and watchlist:
        fits = {
            str(row["url"]): row["_fit"]
            for row in watchlist
            if isinstance(row.get("_fit"), FitCheckResponse)
        }
        written = write_watchlist_cvs(watchlist, args.cv_out, fits=fits)
        cv_paths = [str(path) for path in written]
        print(f"\nwatchlist CVs: {len(written)} → {args.cv_out}")
        for path in written:
            print(f"  {path}")
    elif args.cv_from_watchlist:
        print("\nwatchlist CVs: 0 (no watchlist rows)")

    cv_passed_paths: list[str] = []
    if args.cv_from_passed and passed:
        fits_passed = {
            str(row["url"]): row["_fit"]
            for row in passed
            if isinstance(row.get("_fit"), FitCheckResponse)
        }
        written_passed = write_passed_cvs(
            passed, args.cv_out_passed, fits=fits_passed
        )
        cv_passed_paths = [str(path) for path in written_passed]
        print(f"\npassed CVs: {len(written_passed)} → {args.cv_out_passed}")
        for path in written_passed:
            print(f"  {path}")
    elif args.cv_from_passed:
        print("\npassed CVs: 0 (no passed rows)")

    passed_out = _strip_private_fields(passed)
    rejected_out = _strip_private_fields(rejected)
    watchlist_out = _strip_private_fields(watchlist)

    payload: dict[str, Any] = {
        "board_url": board_url,
        "fit_check_enabled": args.fit_check,
        "include_weak_proceed": args.include_weak_proceed,
        "cv_from_watchlist": args.cv_from_watchlist,
        "cv_from_passed": args.cv_from_passed,
        "discovered": len(listings),
        "prefilter_rejected_count": len(prefilter_rejected),
        "candidates_after_prefilter": candidates_after_prefilter,
        "fit_checked": len(to_process),
        "limit": args.limit,
        "limit_applied_after_prefilter": True,
        "limited": limited,
        "processed": len(rows),
        "passed_count": len(passed),
        "watchlist_count": len(watchlist) if args.include_weak_proceed else 0,
        "rejected_count": len(rejected),
        "passed": passed_out,
        "rejected": rejected_out,
    }
    if args.include_weak_proceed:
        payload["watchlist"] = watchlist_out
    if args.cv_from_watchlist:
        payload["cv_out"] = str(args.cv_out)
        payload["cv_watchlist_count"] = len(cv_paths)
        payload["cv_watchlist_paths"] = cv_paths
    if args.cv_from_passed:
        payload["cv_out_passed"] = str(args.cv_out_passed)
        payload["cv_passed_count"] = len(cv_passed_paths)
        payload["cv_passed_paths"] = cv_passed_paths

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwritten: {args.out}")
    if args.include_weak_proceed:
        print(
            f"passed: {len(passed)} | watchlist: {len(watchlist)} | rejected: {len(rejected)}"
        )
    else:
        print(f"passed: {len(passed)} | rejected: {len(rejected)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
