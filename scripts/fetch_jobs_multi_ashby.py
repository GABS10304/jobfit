"""Multi-board Ashby sourcing runner (official public Job Posting API).

boards from domain/ashby_boards.yaml → one API call per board (full JDs
included) → excluded-company gate → title prefilter → V3 fit-check →
passed/watchlist/rejected. Output shape matches the other multi-board
runners, so scripts/build_daily_shortlist.py consumes it unchanged.

Usage:
  python scripts/fetch_jobs_multi_ashby.py --out out/daily/ashby_20261017.json
  python scripts/fetch_jobs_multi_ashby.py --board-ids skalar
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
from scripts.fetch_jobs_multi_join import _bucket  # noqa: E402
from backend import data_loader  # noqa: E402
from backend.sourcing import ashby  # noqa: E402
from backend.sourcing.filtering import evaluate_title_prefilter, is_excluded_company  # noqa: E402

DEFAULT_BOARDS_FILE = REPO_ROOT / "domain" / "ashby_boards.yaml"
DEFAULT_DELAY_BETWEEN_BOARDS = 2.0


def load_boards(path: Path) -> list[dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: list[dict[str, Any]] = []
    for entry in raw.get("boards") or []:
        if not isinstance(entry, dict) or entry.get("disabled") is True:
            continue
        board_id = str(entry.get("id") or "").strip()
        url = str(entry.get("url") or "").strip()
        if not board_id or not url or not ashby.is_ashby_board_url(url):
            continue
        out.append({"id": board_id, "name": entry.get("name") or board_id, "url": url})
    if not out:
        raise ValueError(f"No valid Ashby boards in {path}")
    return out


def process_board(
    board: dict[str, Any],
    *,
    fit_check: bool,
    excluded_companies: list[str] | None,
    discover=ashby.discover_jobs,
) -> dict[str, Any]:
    print(f"\n=== Ashby board {board['id']} ({board['url']}) ===")
    base = {"id": board["id"], "name": board["name"], "url": board["url"]}
    empty = {"discovered": 0, "passed": [], "watchlist": [], "rejected": []}

    if is_excluded_company(board["name"], excluded_companies) or is_excluded_company(
        board["id"], excluded_companies
    ):
        print("  skip: excluded_company")
        return {**base, "status": "skipped", "error": "excluded_company", **empty}

    try:
        pairs = discover(board["url"], company=board["name"])
    except Exception as exc:  # never kill the daily run over one board
        print(f"  skip: {exc}")
        return {**base, "status": "error", "error": str(exc), **empty}

    rows: list[dict[str, Any]] = []
    checked = 0
    for listing, job in pairs:
        passes, reason = evaluate_title_prefilter(listing.title)
        if not passes:
            rows.append({"url": listing.url, "status": "rejected", "title": listing.title,
                         "company": board["name"], "passes_default_filter": False,
                         "sourcing_bucket": "rejected", "reject_reason": reason or "title_prefilter"})
            continue
        entry: dict[str, Any] = {"url": job.url, "status": "ok", "title": job.title,
                                 "company": board["name"], "job": job.to_dict()}
        if fit_check:
            _fit, payload = _run_fit_check(job)
            _bucket(entry, payload)
        else:
            entry.update(passes_default_filter=True, watchlist=False, sourcing_bucket="passed")
        checked += 1
        rows.append(entry)

    passed = [r for r in rows if r.get("sourcing_bucket") == "passed"]
    watchlist = [r for r in rows if r.get("sourcing_bucket") == "watchlist"]
    rejected = [r for r in rows if r.get("sourcing_bucket") not in ("passed", "watchlist")]
    print(f"  discovered {len(pairs)}; fit-checked {checked}; passed {len(passed)} | "
          f"watchlist {len(watchlist)} | rejected {len(rejected)}")
    return {
        **base,
        "status": "ok",
        "discovered": len(pairs),
        "fit_checked": checked,
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
    parser.add_argument("--delay-between-boards", type=float, default=DEFAULT_DELAY_BETWEEN_BOARDS)
    parser.add_argument("--out", type=Path, default=Path("multi_ashby_results.json"))
    args = parser.parse_args()

    boards = load_boards(args.boards_file)
    if args.board_ids:
        wanted = {b.casefold() for b in args.board_ids}
        boards = [b for b in boards if b["id"].casefold() in wanted]
        if not boards:
            print("No boards matched --board-ids.", file=sys.stderr)
            return 1

    excluded = data_loader.load_constraints().excluded_companies
    print(f"multi-ashby run: {len(boards)} board(s)")
    results: list[dict[str, Any]] = []
    for index, board in enumerate(boards):
        if index > 0 and args.delay_between_boards > 0:
            time.sleep(args.delay_between_boards)
        results.append(process_board(board, fit_check=args.fit_check, excluded_companies=excluded))

    all_passed = [{**r, "board_id": b["id"]} for b in results for r in b.get("passed") or []]
    all_watch = [{**r, "board_id": b["id"]} for b in results for r in b.get("watchlist") or []]
    overall = {
        "boards_tried": len(results),
        "boards_ok": sum(1 for b in results if b.get("status") == "ok"),
        "discovered": sum(int(b.get("discovered") or 0) for b in results),
        "fit_checked": sum(int(b.get("fit_checked") or 0) for b in results),
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
