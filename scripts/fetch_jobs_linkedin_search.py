"""Run one LinkedIn guest-search query and optionally fit-check the results.

Same shape as fetch_jobs_workday_board.py's board processor, but backed by
backend.sourcing.linkedin instead of a Personio/Workday board — search
results already carry title + company, so (unlike Personio) no per-job
title-only fetch is needed before the prefilter.

Usage:
  python scripts/fetch_jobs_linkedin_search.py --query "AI Product Manager" \\
      --location Germany --jobage-days 3 --out /tmp/li.json

Personal-use only — see backend/sourcing/linkedin.py. Keep --limit and
--delay conservative; this hits LinkedIn's public guest endpoints directly.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.fetch_jobs_batch import _run_fit_check, _strip_private_fields  # noqa: E402
from backend import data_loader  # noqa: E402
from backend.sourcing import linkedin  # noqa: E402
from backend.sourcing.filtering import evaluate_title_prefilter, is_excluded_company  # noqa: E402
from backend.tracking.seen_cache import DEFAULT_TTL_DAYS, SeenCache  # noqa: E402

DEFAULT_DELAY_SEC = 1.5


def _process_job(
    url: str,
    *,
    fit_check: bool,
    listing_title: str | None = None,
    listing_company: str | None = None,
) -> dict[str, Any]:
    try:
        job, detail_company = linkedin.fetch_job_detail(url)
    except Exception as exc:
        return {
            "url": url,
            "status": "error",
            "title": listing_title,
            "company": listing_company,
            "error": str(exc),
            "passes_default_filter": False,
            "reject_reason": f"fetch_error: {exc}",
        }

    entry: dict[str, Any] = {
        "url": url,
        "status": "ok",
        "title": job.title,
        "company": listing_company or detail_company,
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


def run_search(
    *,
    query: str | None,
    location: str | None,
    jobage_days: int | None,
    remote: str | None,
    limit: int | None,
    fit_check: bool,
    delay: float,
    pages: int = 1,
    seen: SeenCache | None = None,
    seen_ttl_days: int = DEFAULT_TTL_DAYS,
) -> dict[str, Any]:
    print(f"=== LinkedIn search: query={query!r} location={location!r} pages={pages} ===")
    excluded_companies = data_loader.load_constraints().excluded_companies

    # Page through results (10 per page). One page used to be the only page,
    # so on broad queries like "Product Manager / Germany" most postings were
    # never seen at all. Stop early when a page comes back short or repeats.
    listings = []
    seen_urls: set[str] = set()
    for page in range(1, max(1, pages) + 1):
        if page > 1 and delay > 0:
            time.sleep(delay)
        page_listings = linkedin.search_jobs(
            query=query, location=location, jobage_days=jobage_days, remote=remote, page=page
        )
        fresh = [item for item in page_listings if item.url not in seen_urls]
        seen_urls.update(item.url for item in fresh)
        listings.extend(fresh)
        if len(page_listings) < 10 or not fresh:
            break
    print(f"  discovered {len(listings)}; title prefilter...")

    candidates = []
    rejected: list[dict[str, Any]] = []
    skipped_seen = 0
    for listing in listings:
        if is_excluded_company(listing.company, excluded_companies):
            rejected.append(
                {
                    "url": listing.url,
                    "status": "rejected",
                    "title": listing.title,
                    "company": listing.company,
                    "passes_default_filter": False,
                    "reject_reason": "excluded_company",
                }
            )
            continue
        passes, reason = evaluate_title_prefilter(listing.title)
        if not passes:
            rejected.append(
                {
                    "url": listing.url,
                    "status": "rejected",
                    "title": listing.title,
                    "company": listing.company,
                    "passes_default_filter": False,
                    "reject_reason": reason or "title_prefilter",
                }
            )
            continue
        if seen is not None and seen.is_fresh(listing.url, seen_ttl_days):
            skipped_seen += 1
            continue
        candidates.append(listing)

    print(
        f"  prefilter: {len(candidates)} candidate(s), {len(rejected)} rejected, "
        f"{skipped_seen} skipped (checked <{seen_ttl_days}d ago)"
    )

    limited = limit is not None and len(candidates) > limit
    to_process = candidates[:limit] if limit is not None else candidates

    rows: list[dict[str, Any]] = list(rejected)
    for index, listing in enumerate(to_process):
        if index > 0 and delay > 0:
            time.sleep(delay)
        row = _process_job(
            listing.url,
            fit_check=fit_check,
            listing_title=listing.title,
            listing_company=listing.company,
        )
        if seen is not None and row.get("status") == "ok":
            seen.mark(listing.url)
        rows.append(row)

    passed = [r for r in rows if r.get("sourcing_bucket") == "passed"]
    watchlist = [r for r in rows if r.get("sourcing_bucket") == "watchlist"]
    rejected_all = [r for r in rows if r.get("sourcing_bucket") not in ("passed", "watchlist")]

    print(
        f"  totals — passed: {len(passed)} | watchlist: {len(watchlist)} | "
        f"rejected: {len(rejected_all)}"
    )

    return {
        "query": query,
        "location": location,
        "status": "ok",
        "discovered": len(listings),
        "candidates_after_prefilter": len(candidates) + skipped_seen,
        "skipped_seen": skipped_seen,
        "fit_checked": len(to_process),
        "limited": limited,
        "passed_count": len(passed),
        "watchlist_count": len(watchlist),
        "rejected_count": len(rejected_all),
        "passed": _strip_private_fields(passed),
        "watchlist": _strip_private_fields(watchlist),
        "rejected": _strip_private_fields(rejected_all),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default=None)
    parser.add_argument("--location", default=None)
    parser.add_argument("--jobage-days", type=int, default=None)
    parser.add_argument("--remote", default=None, choices=["remote", "hybrid", "onsite"])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--pages", type=int, default=1, help="Result pages to read (10/page)")
    parser.add_argument(
        "--fit-check", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SEC)
    parser.add_argument("--out", type=Path, default=Path("results_linkedin.json"))
    args = parser.parse_args()

    result = run_search(
        query=args.query,
        location=args.location,
        jobage_days=args.jobage_days,
        remote=args.remote,
        limit=args.limit,
        fit_check=args.fit_check,
        delay=args.delay,
        pages=args.pages,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
