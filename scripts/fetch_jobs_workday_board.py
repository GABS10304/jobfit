"""Fetch jobs from a Workday careers board (CXS discovery) and optionally fit-check.

Usage:
  python scripts/fetch_jobs_workday_board.py \\
      --board-url https://ing.wd3.myworkdayjobs.com/de-DE/ICSGBLCOR \\
      --limit 5 --fit-check --out /tmp/workday_board.json
  python scripts/fetch_jobs_workday_board.py --urls-file urls.txt --fit-check
  python scripts/fetch_jobs_workday_board.py --board-url <url> --search-text "Product Manager"

Reuses Personio batch patterns: title prefilter → V3 fit-check → sourcing filter.
CXS listings include titles, so prefilter usually needs no per-job title fetch.
--limit N applies AFTER title prefilter (N product-ish candidates).
When --limit is set, CXS pagination stops once enough prefilter candidates exist.
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

from scripts.fetch_jobs_batch import (  # noqa: E402
    _load_urls_from_file,
    _prefilter_listings,
    _print_summary_table,
    _run_fit_check,
    _strip_private_fields,
)
from backend.models import FitCheckResponse  # noqa: E402
from backend.generation.watchlist_cv import write_passed_cvs, write_watchlist_cvs  # noqa: E402
from backend.sourcing.personio import JobListing  # noqa: E402
from backend.sourcing.workday import (  # noqa: E402
    CXS_PAGE_SIZE,
    fetch_cxs_jobs,
    fetch_workday_job,
    listings_from_cxs_payload,
    parse_workday_board_url,
)


def _process_job(
    url: str,
    *,
    use_playwright: bool,
    fit_check: bool,
    listing_title: str | None = None,
) -> dict[str, Any]:
    """Same shape as Personio batch processor, but fetches via Workday."""
    try:
        job = fetch_workday_job(url, use_playwright=use_playwright)
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


def _discover_with_prefilter(
    board_url: str,
    *,
    search_text: str,
    limit: int | None,
    use_playwright: bool,
) -> tuple[list[JobListing], list[JobListing], list[dict[str, Any]], int]:
    """Paginate CXS, title-prefilter as we go; stop when enough candidates.

    Returns (all_seen_listings, candidates, prefilter_rejected, discovered_count).
    """
    board = parse_workday_board_url(board_url)
    all_listings: list[JobListing] = []
    candidates: list[JobListing] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()
    offset = 0
    total: int | None = None

    while True:
        if limit is not None and len(candidates) >= limit:
            break

        payload = fetch_cxs_jobs(
            board,
            offset=offset,
            limit=CXS_PAGE_SIZE,
            search_text=search_text,
        )
        if total is None:
            raw_total = payload.get("total")
            total = int(raw_total) if isinstance(raw_total, int) else None

        page_listings = listings_from_cxs_payload(payload, board)
        if not page_listings:
            break

        fresh: list[JobListing] = []
        for listing in page_listings:
            if listing.url in seen:
                continue
            seen.add(listing.url)
            all_listings.append(listing)
            fresh.append(listing)

        page_candidates, page_rejected = _prefilter_listings(
            fresh, use_playwright=use_playwright
        )
        candidates.extend(page_candidates)
        rejected.extend(page_rejected)

        offset += CXS_PAGE_SIZE
        if total is not None and offset >= total:
            break
        if len(page_listings) < CXS_PAGE_SIZE:
            break

    return all_listings, candidates, rejected, len(all_listings)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch-fetch Workday board jobs (CXS) and apply sourcing filter.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--board-url",
        help="Workday careers board URL (e.g. https://tenant.wd3.myworkdayjobs.com/de-DE/Site)",
    )
    source.add_argument(
        "--urls-file",
        type=Path,
        help="Fallback: text file with one Workday job URL per line (no CXS)",
    )
    parser.add_argument(
        "--search-text",
        default="",
        help="Optional CXS searchText to narrow listings (board mode only)",
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
        default=Path("results_workday.json"),
        help="Write JSON results to this path (default: results_workday.json)",
    )
    parser.add_argument(
        "--playwright",
        action="store_true",
        help="Force Playwright for individual job fetch fallback",
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
        help="Write labeled weak-match CVs for watchlist rows under --cv-out.",
    )
    parser.add_argument(
        "--cv-from-passed",
        action="store_true",
        help="Write labeled passed CVs under --cv-out-passed.",
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
    discovery_mode = "cxs" if args.board_url else "urls_file"

    if args.board_url:
        print(f"CXS discover: {args.board_url}")
        if args.search_text:
            print(f"searchText={args.search_text!r}")
        listings, candidates, prefilter_rejected, discovered = _discover_with_prefilter(
            args.board_url,
            search_text=args.search_text,
            limit=args.limit,
            use_playwright=args.playwright,
        )
    else:
        listings = _load_urls_from_file(args.urls_file)
        discovered = len(listings)
        if not listings:
            print("No job URLs to process.", file=sys.stderr)
            return 1
        print(f"loaded {discovered} URL(s) from file; running title prefilter...")
        candidates, prefilter_rejected = _prefilter_listings(
            listings, use_playwright=args.playwright
        )

    candidates_after_prefilter = len(candidates)
    print(
        f"discovered {discovered} listing(s); "
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
    elif args.cv_from_passed:
        print("\npassed CVs: 0 (no passed rows)")

    payload: dict[str, Any] = {
        "board_url": board_url,
        "discovery_mode": discovery_mode,
        "search_text": args.search_text or None,
        "fit_check_enabled": args.fit_check,
        "include_weak_proceed": args.include_weak_proceed,
        "cv_from_watchlist": args.cv_from_watchlist,
        "cv_from_passed": args.cv_from_passed,
        "discovered": discovered,
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
        "passed": _strip_private_fields(passed),
        "rejected": _strip_private_fields(rejected),
    }
    if args.include_weak_proceed:
        payload["watchlist"] = _strip_private_fields(watchlist)
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
