"""Run all LinkedIn guest-search queries from domain/linkedin_searches.yaml.

Same shape as fetch_jobs_multi_workday.py: loads a small YAML list of
searches, runs each through fetch_jobs_linkedin_search.run_search, aggregates
passed/watchlist rows into one artifact for build_daily_shortlist.py.

Personal-use only (see backend/sourcing/linkedin.py) — this is why the
searches file is deliberately short and --delay-between-searches defaults
higher than the Personio/Workday multi-board runners.

Usage:
  python scripts/fetch_jobs_multi_linkedin.py --out out/daily/linkedin_20260801.json
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

from scripts.fetch_jobs_linkedin_search import run_search  # noqa: E402
from backend.tracking.seen_cache import DEFAULT_TTL_DAYS, SeenCache  # noqa: E402

DEFAULT_SEARCHES_FILE = REPO_ROOT / "domain" / "linkedin_searches.yaml"
DEFAULT_DELAY_BETWEEN_SEARCHES = 5.0


def load_searches(path: Path) -> list[dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    searches = raw.get("searches") or []
    if not isinstance(searches, list) or not searches:
        raise ValueError(f"No searches listed in {path}")
    out: list[dict[str, Any]] = []
    for entry in searches:
        if not isinstance(entry, dict) or entry.get("disabled") is True:
            continue
        search_id = str(entry.get("id") or "").strip()
        if not search_id:
            continue
        out.append(
            {
                "id": search_id,
                "name": entry.get("name") or search_id,
                "query": entry.get("query"),
                "location": entry.get("location"),
                "jobage_days": entry.get("jobage_days"),
                "remote": entry.get("remote"),
                "pages": int(entry.get("pages") or 1),
            }
        )
    if not out:
        raise ValueError(f"No enabled search entries in {path}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--searches-file", type=Path, default=DEFAULT_SEARCHES_FILE)
    parser.add_argument("--search-ids", nargs="*", default=None)
    parser.add_argument("--limit-per-search", type=int, default=None)
    parser.add_argument(
        "--fit-check", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--delay", type=float, default=1.5, help="Delay between job detail fetches")
    parser.add_argument(
        "--delay-between-searches", type=float, default=DEFAULT_DELAY_BETWEEN_SEARCHES
    )
    parser.add_argument("--out", type=Path, default=Path("multi_linkedin_results.json"))
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Cap per-search 'pages' from YAML (e.g. 1 for a quick run)",
    )
    parser.add_argument(
        "--seen-cache",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip jobs already fit-checked within --seen-ttl-days (default: on)",
    )
    parser.add_argument("--seen-ttl-days", type=int, default=DEFAULT_TTL_DAYS)
    args = parser.parse_args()
    seen = SeenCache() if args.seen_cache else None

    searches = load_searches(args.searches_file)
    if args.search_ids:
        wanted = {sid.casefold() for sid in args.search_ids}
        searches = [s for s in searches if s["id"].casefold() in wanted]
        if not searches:
            print("No searches matched --search-ids.", file=sys.stderr)
            return 1

    print(f"multi-linkedin run: {len(searches)} search(es)")

    search_results: list[dict[str, Any]] = []
    for index, search in enumerate(searches):
        if index > 0 and args.delay_between_searches > 0:
            time.sleep(args.delay_between_searches)
        result = run_search(
            query=search["query"],
            location=search["location"],
            jobage_days=search["jobage_days"],
            remote=search["remote"],
            limit=args.limit_per_search,
            fit_check=args.fit_check,
            delay=args.delay,
            pages=min(search["pages"], args.max_pages) if args.max_pages else search["pages"],
            seen=seen,
            seen_ttl_days=args.seen_ttl_days,
        )
        result["id"] = search["id"]
        result["name"] = search["name"]
        search_results.append(result)

    if seen is not None:
        seen.save()

    overall = {
        "searches_tried": len(search_results),
        "discovered": sum(int(s.get("discovered") or 0) for s in search_results),
        "candidates_after_prefilter": sum(
            int(s.get("candidates_after_prefilter") or 0) for s in search_results
        ),
        "fit_checked": sum(int(s.get("fit_checked") or 0) for s in search_results),
        "skipped_seen": sum(int(s.get("skipped_seen") or 0) for s in search_results),
        "passed_count": sum(int(s.get("passed_count") or 0) for s in search_results),
        "watchlist_count": sum(int(s.get("watchlist_count") or 0) for s in search_results),
        "rejected_count": sum(int(s.get("rejected_count") or 0) for s in search_results),
    }

    all_passed: list[dict[str, Any]] = []
    all_watchlist: list[dict[str, Any]] = []
    for search in search_results:
        all_passed.extend(search.get("passed") or [])
        all_watchlist.extend(search.get("watchlist") or [])

    payload: dict[str, Any] = {
        "searches_file": str(args.searches_file),
        "searches": search_results,
        "overall": overall,
        "passed": all_passed,
        "watchlist": all_watchlist,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        f"=== overall ===\n"
        f"searches ok: {overall['searches_tried']}\n"
        f"discovered={overall['discovered']} fit_checked={overall['fit_checked']} "
        f"passed={overall['passed_count']} watchlist={overall['watchlist_count']} "
        f"rejected={overall['rejected_count']}\n"
        f"written: {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
