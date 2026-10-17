"""Multi-board JOIN (join.com) sourcing runner.

Same shape as fetch_jobs_multi_board.py (Personio) / fetch_jobs_multi_linkedin.py:
boards from domain/join_boards.yaml → paginated discovery → excluded-company
gate → title prefilter → skip recently-checked jobs (seen cache) → detail
fetch → V3 fit-check → passed/watchlist/rejected. The aggregate artifact feeds
scripts/build_daily_shortlist.py unchanged.

Usage:
  python scripts/fetch_jobs_multi_join.py --out out/daily/join_20261017.json
  python scripts/fetch_jobs_multi_join.py --board-ids skalar --no-seen-cache
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

import yaml  # noqa: E402

from scripts.fetch_jobs_batch import _run_fit_check, _strip_private_fields  # noqa: E402
from backend import data_loader  # noqa: E402
from backend.sourcing import join  # noqa: E402
from backend.sourcing.filtering import evaluate_title_prefilter, is_excluded_company  # noqa: E402
from backend.tracking.seen_cache import DEFAULT_TTL_DAYS, SeenCache  # noqa: E402

DEFAULT_BOARDS_FILE = REPO_ROOT / "domain" / "join_boards.yaml"
DEFAULT_DELAY_SEC = 1.5
DEFAULT_DELAY_BETWEEN_BOARDS = 3.0


def load_boards(path: Path) -> list[dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: list[dict[str, Any]] = []
    for entry in raw.get("boards") or []:
        if not isinstance(entry, dict) or entry.get("disabled") is True:
            continue
        board_id = str(entry.get("id") or "").strip()
        url = str(entry.get("url") or "").strip()
        if not board_id or not url or not join.is_join_board_url(url):
            continue
        out.append({"id": board_id, "name": entry.get("name") or board_id, "url": url})
    if not out:
        raise ValueError(f"No valid JOIN boards in {path}")
    return out


def _bucket(entry: dict[str, Any], fit_payload: dict[str, Any]) -> None:
    entry["fit_check"] = fit_payload
    entry["passes_default_filter"] = fit_payload["passes_default_filter"]
    entry["watchlist"] = bool(fit_payload.get("watchlist_eligible"))
    if entry["passes_default_filter"]:
        entry["sourcing_bucket"] = "passed"
    elif entry["watchlist"]:
        entry["sourcing_bucket"] = "watchlist"
        detail = fit_payload.get("watchlist_reason") or fit_payload.get("filter_reject_reason")
        entry["reject_reason"] = f"watchlist: {detail}"
    else:
        entry["sourcing_bucket"] = "rejected"
        detail = fit_payload.get("filter_reject_reason") or fit_payload["status_flag"]
        entry["reject_reason"] = f"filter: {detail}"


def _process_job(url: str, *, company: str, listing_title: str | None, fit_check: bool) -> dict[str, Any]:
    try:
        job, detail_company = join.fetch_join_job(url)
    except Exception as exc:
        return {
            "url": url,
            "status": "error",
            "title": listing_title,
            "company": company,
            "error": str(exc),
            "passes_default_filter": False,
            "sourcing_bucket": "rejected",
            "reject_reason": f"fetch_error: {exc}",
        }
    entry: dict[str, Any] = {
        "url": url,
        "status": "ok",
        "title": job.title,
        "company": company or detail_company,
        "job": job.to_dict(),
    }
    if fit_check:
        _fit, payload = _run_fit_check(job)
        _bucket(entry, payload)
    else:
        entry.update(passes_default_filter=True, watchlist=False, sourcing_bucket="passed")
    return entry


def process_board(
    board: dict[str, Any],
    *,
    fit_check: bool,
    delay: float,
    max_pages: int,
    seen: SeenCache | None,
    seen_ttl_days: int,
    excluded_companies: list[str] | None,
) -> dict[str, Any]:
    print(f"\n=== JOIN board {board['id']} ({board['url']}) ===")
    base = {"id": board["id"], "name": board["name"], "url": board["url"]}

    if is_excluded_company(board["name"], excluded_companies) or is_excluded_company(
        board["id"], excluded_companies
    ):
        print("  skip: excluded_company")
        return {**base, "status": "skipped", "error": "excluded_company", "discovered": 0,
                "passed": [], "watchlist": [], "rejected": []}

    try:
        listings = join.discover_job_listings(board["url"], company=board["name"], max_pages=max_pages)
    except Exception as exc:  # dead board / network → skip, never kill the daily run
        print(f"  skip: {exc}")
        return {**base, "status": "error", "error": str(exc), "discovered": 0,
                "passed": [], "watchlist": [], "rejected": []}

    candidates = []
    rows: list[dict[str, Any]] = []
    skipped_seen = 0
    for listing in listings:
        passes, reason = evaluate_title_prefilter(listing.title)
        if not passes:
            rows.append({"url": listing.url, "status": "rejected", "title": listing.title,
                         "company": board["name"], "passes_default_filter": False,
                         "sourcing_bucket": "rejected", "reject_reason": reason or "title_prefilter"})
            continue
        if seen is not None and seen.is_fresh(listing.url, seen_ttl_days):
            skipped_seen += 1
            continue
        candidates.append(listing)
    print(f"  discovered {len(listings)}; candidates {len(candidates)}; "
          f"skipped (checked <{seen_ttl_days}d ago) {skipped_seen}")

    for index, listing in enumerate(candidates):
        if index > 0 and delay > 0:
            time.sleep(delay)
        row = _process_job(listing.url, company=board["name"], listing_title=listing.title,
                           fit_check=fit_check)
        if seen is not None and row.get("status") == "ok":
            seen.mark(listing.url)
        rows.append(row)

    passed = [r for r in rows if r.get("sourcing_bucket") == "passed"]
    watchlist = [r for r in rows if r.get("sourcing_bucket") == "watchlist"]
    rejected = [r for r in rows if r.get("sourcing_bucket") not in ("passed", "watchlist")]
    print(f"  totals — passed: {len(passed)} | watchlist: {len(watchlist)} | rejected: {len(rejected)}")
    return {
        **base,
        "status": "ok",
        "discovered": len(listings),
        "candidates_after_prefilter": len(candidates) + skipped_seen,
        "skipped_seen": skipped_seen,
        "fit_checked": len(candidates),
        "passed_count": len(passed),
        "watchlist_count": len(watchlist),
        "rejected_count": len(rejected),
        "passed": _strip_private_fields(passed),
        "watchlist": _strip_private_fields(watchlist),
        "rejected": _strip_private_fields(rejected),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boards-file", type=Path, default=DEFAULT_BOARDS_FILE)
    parser.add_argument("--board-ids", nargs="*", default=None)
    parser.add_argument("--fit-check", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SEC,
                        help="Seconds between job detail fetches")
    parser.add_argument("--delay-between-boards", type=float, default=DEFAULT_DELAY_BETWEEN_BOARDS)
    parser.add_argument("--max-pages", type=int, default=join.DEFAULT_MAX_PAGES)
    parser.add_argument("--seen-cache", action=argparse.BooleanOptionalAction, default=True,
                        help="Skip jobs already fit-checked within --seen-ttl-days (default: on)")
    parser.add_argument("--seen-ttl-days", type=int, default=DEFAULT_TTL_DAYS)
    parser.add_argument("--out", type=Path, default=Path("multi_join_results.json"))
    args = parser.parse_args()

    boards = load_boards(args.boards_file)
    if args.board_ids:
        wanted = {b.casefold() for b in args.board_ids}
        boards = [b for b in boards if b["id"].casefold() in wanted]
        if not boards:
            print("No boards matched --board-ids.", file=sys.stderr)
            return 1

    seen = SeenCache() if args.seen_cache else None
    excluded = data_loader.load_constraints().excluded_companies
    print(f"multi-join run: {len(boards)} board(s)")

    results: list[dict[str, Any]] = []
    for index, board in enumerate(boards):
        if index > 0 and args.delay_between_boards > 0:
            time.sleep(args.delay_between_boards)
        results.append(process_board(board, fit_check=args.fit_check, delay=args.delay,
                                     max_pages=args.max_pages, seen=seen,
                                     seen_ttl_days=args.seen_ttl_days,
                                     excluded_companies=excluded))
    if seen is not None:
        seen.save()

    all_passed = [{**r, "board_id": b["id"]} for b in results for r in b.get("passed") or []]
    all_watch = [{**r, "board_id": b["id"]} for b in results for r in b.get("watchlist") or []]
    overall = {
        "boards_tried": len(results),
        "boards_ok": sum(1 for b in results if b.get("status") == "ok"),
        "discovered": sum(int(b.get("discovered") or 0) for b in results),
        "fit_checked": sum(int(b.get("fit_checked") or 0) for b in results),
        "skipped_seen": sum(int(b.get("skipped_seen") or 0) for b in results),
        "passed_count": len(all_passed),
        "watchlist_count": len(all_watch),
    }
    payload = {"boards_file": str(args.boards_file), "overall": overall, "boards": results,
               "passed": all_passed, "watchlist": all_watch}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== overall ===\n{overall}\nwritten: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
