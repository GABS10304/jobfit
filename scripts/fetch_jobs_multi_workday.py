"""Multi-board Workday sourcing runner.

Loads boards from domain/workday_boards.yaml, runs CXS discovery → title
prefilter → V3 fit-check → watchlist per board, aggregates counts.

Usage:
  python scripts/fetch_jobs_multi_workday.py --out /tmp/multi_workday_e2e.json
  python scripts/fetch_jobs_multi_workday.py --limit-per-board 3 --delay 2.0
  python scripts/fetch_jobs_multi_workday.py --search-text "Product Manager"
  python scripts/fetch_jobs_multi_workday.py --no-include-weak-proceed

Defaults:
  --search-text "Product Manager"
  --include-weak-proceed ON (watchlist is primary output until strong passes exist)
  --boards-file domain/workday_boards.yaml
  Dead / rate-limited / WAF boards are skipped gracefully (board status=error|skipped).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.fetch_jobs_batch import (  # noqa: E402
    _print_summary_table,
    _strip_private_fields,
)
from scripts.fetch_jobs_workday_board import (  # noqa: E402
    _discover_with_prefilter,
    _process_job,
)
from backend.generation.watchlist_cv import write_passed_cvs  # noqa: E402

DEFAULT_BOARDS_FILE = REPO_ROOT / "domain" / "workday_boards.yaml"
DEFAULT_SEARCH_TEXT = "Product Manager"
DEFAULT_DELAY_SEC = 2.0
DEFAULT_BACKOFF_SEC = 8.0
MAX_BOARD_RETRIES = 2
DEFAULT_CV_PASSED_OUT = REPO_ROOT / "out" / "cv_passed"


def load_boards(path: Path) -> list[dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    boards = raw.get("boards") or []
    if not isinstance(boards, list) or not boards:
        raise ValueError(f"No boards listed in {path}")
    out: list[dict[str, Any]] = []
    for entry in boards:
        if not isinstance(entry, dict):
            continue
        if entry.get("disabled") is True:
            continue
        url = str(entry.get("url") or "").strip()
        board_id = str(entry.get("id") or "").strip()
        if not url or not board_id:
            continue
        out.append(
            {
                "id": board_id,
                "name": str(entry.get("name") or board_id),
                "url": url,
                "region": entry.get("region"),
                "notes": entry.get("notes"),
            }
        )
    if not out:
        raise ValueError(f"No valid board entries in {path}")
    return out


def _looks_transient(exc: BaseException) -> bool:
    text = str(exc).casefold()
    return any(
        token in text
        for token in (
            "429",
            "timeout",
            "temporar",
            "rate",
            "503",
            "502",
            "connect",
            "jsondecode",
            "expecting value",
            "html",
        )
    )


def _discover_with_backoff(
    board_url: str,
    *,
    search_text: str,
    limit_per_board: int | None,
    use_playwright: bool,
    backoff_sec: float,
) -> tuple[list[Any], list[Any], list[dict[str, Any]], int, str | None]:
    """Return (listings, candidates, prefilter_rejected, discovered, error)."""
    last_error: str | None = None
    for attempt in range(MAX_BOARD_RETRIES + 1):
        try:
            listings, candidates, rejected, discovered = _discover_with_prefilter(
                board_url,
                search_text=search_text,
                limit=limit_per_board,
                use_playwright=use_playwright,
            )
            return listings, candidates, rejected, discovered, None
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            last_error = f"http_{status}: {exc}"
            if status in {429, 502, 503} and attempt < MAX_BOARD_RETRIES:
                wait = backoff_sec * (attempt + 1)
                print(
                    f"  backoff {wait:.1f}s after HTTP {status} "
                    f"(attempt {attempt + 1}/{MAX_BOARD_RETRIES + 1})"
                )
                time.sleep(wait)
                continue
            return [], [], [], 0, last_error
        except Exception as exc:
            last_error = str(exc)
            if attempt < MAX_BOARD_RETRIES and _looks_transient(exc):
                wait = backoff_sec * (attempt + 1)
                print(f"  backoff {wait:.1f}s after {type(exc).__name__}: {exc}")
                time.sleep(wait)
                continue
            return [], [], [], 0, last_error
    return [], [], [], 0, last_error or "unknown_discover_error"


def _bucket_rows(
    rows: list[dict[str, Any]],
    *,
    include_weak_proceed: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    passed = [row for row in rows if row.get("passes_default_filter")]
    watchlist = [
        row
        for row in rows
        if include_weak_proceed
        and row.get("watchlist")
        and not row.get("passes_default_filter")
    ]
    watchlist_urls = {row["url"] for row in watchlist}
    rejected = [
        row
        for row in rows
        if not row.get("passes_default_filter") and row["url"] not in watchlist_urls
    ]
    return passed, watchlist, rejected


def process_board(
    board: dict[str, Any],
    *,
    search_text: str,
    use_playwright: bool,
    fit_check: bool,
    include_weak_proceed: bool,
    limit_per_board: int | None,
    backoff_sec: float,
) -> dict[str, Any]:
    board_id = board["id"]
    board_url = board["url"]
    print(f"\n=== board {board_id} ({board_url}) ===")
    if search_text:
        print(f"  searchText={search_text!r}")

    listings, candidates, prefilter_rejected, discovered, discover_error = (
        _discover_with_backoff(
            board_url,
            search_text=search_text,
            limit_per_board=limit_per_board,
            use_playwright=use_playwright,
            backoff_sec=backoff_sec,
        )
    )
    if discover_error:
        print(f"  skip: {discover_error}")
        return {
            "id": board_id,
            "name": board.get("name"),
            "url": board_url,
            "status": "error",
            "error": discover_error,
            "search_text": search_text or None,
            "discovered": 0,
            "prefilter_rejected_count": 0,
            "candidates_after_prefilter": 0,
            "fit_checked": 0,
            "passed_count": 0,
            "watchlist_count": 0,
            "rejected_count": 0,
            "passed": [],
            "watchlist": [],
            "rejected": [],
        }

    if not listings:
        print("  skip: no listings (empty board)")
        return {
            "id": board_id,
            "name": board.get("name"),
            "url": board_url,
            "status": "skipped",
            "error": "empty_board",
            "search_text": search_text or None,
            "discovered": 0,
            "prefilter_rejected_count": 0,
            "candidates_after_prefilter": 0,
            "fit_checked": 0,
            "passed_count": 0,
            "watchlist_count": 0,
            "rejected_count": 0,
            "passed": [],
            "watchlist": [],
            "rejected": [],
        }

    candidates_after_prefilter = len(candidates)
    print(
        f"  discovered {discovered}; prefilter: {candidates_after_prefilter} candidate(s), "
        f"{len(prefilter_rejected)} rejected"
    )

    limited = False
    to_process = candidates
    if limit_per_board is not None:
        limited = candidates_after_prefilter > limit_per_board
        to_process = candidates[:limit_per_board]
        print(f"  limit-per-board={limit_per_board}: processing {len(to_process)}")

    rows: list[dict[str, Any]] = list(prefilter_rejected)
    for listing in to_process:
        rows.append(
            _process_job(
                listing.url,
                use_playwright=use_playwright,
                fit_check=fit_check,
                listing_title=listing.title,
            )
        )

    passed, watchlist, rejected = _bucket_rows(
        rows, include_weak_proceed=include_weak_proceed
    )
    _print_summary_table(rows, show_watchlist=include_weak_proceed)

    print(
        f"  board totals — passed: {len(passed)} | "
        f"watchlist: {len(watchlist) if include_weak_proceed else 0} | "
        f"rejected: {len(rejected)}"
    )

    result: dict[str, Any] = {
        "id": board_id,
        "name": board.get("name"),
        "url": board_url,
        "status": "ok",
        "search_text": search_text or None,
        "discovered": discovered,
        "prefilter_rejected_count": len(prefilter_rejected),
        "candidates_after_prefilter": candidates_after_prefilter,
        "fit_checked": len(to_process),
        "limit_per_board": limit_per_board,
        "limited": limited,
        "passed_count": len(passed),
        "watchlist_count": len(watchlist) if include_weak_proceed else 0,
        "rejected_count": len(rejected),
        "passed": _strip_private_fields(passed),
        "rejected": _strip_private_fields(rejected),
    }
    if include_weak_proceed:
        result["watchlist"] = _strip_private_fields(watchlist)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Workday sourcing across multiple boards from YAML (CXS).",
    )
    parser.add_argument(
        "--boards-file",
        type=Path,
        default=DEFAULT_BOARDS_FILE,
        help=f"YAML board list (default: {DEFAULT_BOARDS_FILE})",
    )
    parser.add_argument(
        "--search-text",
        default=DEFAULT_SEARCH_TEXT,
        help=f'CXS searchText (default: "{DEFAULT_SEARCH_TEXT}")',
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("multi_workday_results.json"),
        help="Aggregate JSON output path",
    )
    parser.add_argument(
        "--fit-check",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run V3 fit-check and sourcing filter (default: on)",
    )
    parser.add_argument(
        "--include-weak-proceed",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Include weak product matches as watchlist (default: ON for multi-board). "
            "Does not lower min_top_score. Use --no-include-weak-proceed to disable."
        ),
    )
    parser.add_argument(
        "--limit-per-board",
        type=int,
        default=None,
        help="Process at most N prefilter candidates per board",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY_SEC,
        help=f"Seconds to sleep between boards (default: {DEFAULT_DELAY_SEC})",
    )
    parser.add_argument(
        "--backoff",
        type=float,
        default=DEFAULT_BACKOFF_SEC,
        help=f"Base backoff seconds on 429/5xx/WAF (default: {DEFAULT_BACKOFF_SEC})",
    )
    parser.add_argument(
        "--playwright",
        action="store_true",
        help="Force Playwright for individual job fetch fallback",
    )
    parser.add_argument(
        "--board-ids",
        nargs="*",
        default=None,
        help="Optional subset of board ids from the YAML file",
    )
    parser.add_argument(
        "--cv-from-passed",
        action="store_true",
        help=(
            "For each strong-pass row, run selection_plan + CV render and write "
            "labeled passed markdown under --cv-out-passed."
        ),
    )
    parser.add_argument(
        "--cv-out-passed",
        type=Path,
        default=DEFAULT_CV_PASSED_OUT,
        help=f"Directory for passed CV markdown (default: {DEFAULT_CV_PASSED_OUT})",
    )
    args = parser.parse_args()

    boards = load_boards(args.boards_file)
    if args.board_ids:
        wanted = {bid.casefold() for bid in args.board_ids}
        boards = [b for b in boards if b["id"].casefold() in wanted]
        if not boards:
            print("No boards matched --board-ids.", file=sys.stderr)
            return 1

    print(
        f"multi-workday run: {len(boards)} board(s); "
        f"search_text={args.search_text!r}; "
        f"include_weak_proceed={args.include_weak_proceed}; "
        f"delay={args.delay}s"
    )

    board_results: list[dict[str, Any]] = []
    for index, board in enumerate(boards):
        if index > 0 and args.delay > 0:
            time.sleep(args.delay)
        board_results.append(
            process_board(
                board,
                search_text=args.search_text,
                use_playwright=args.playwright,
                fit_check=args.fit_check,
                include_weak_proceed=args.include_weak_proceed,
                limit_per_board=args.limit_per_board,
                backoff_sec=args.backoff,
            )
        )

    overall = {
        "boards_tried": len(board_results),
        "boards_ok": sum(1 for b in board_results if b.get("status") == "ok"),
        "boards_error": sum(1 for b in board_results if b.get("status") == "error"),
        "boards_skipped": sum(1 for b in board_results if b.get("status") == "skipped"),
        "discovered": sum(int(b.get("discovered") or 0) for b in board_results),
        "prefilter_rejected_count": sum(
            int(b.get("prefilter_rejected_count") or 0) for b in board_results
        ),
        "candidates_after_prefilter": sum(
            int(b.get("candidates_after_prefilter") or 0) for b in board_results
        ),
        "fit_checked": sum(int(b.get("fit_checked") or 0) for b in board_results),
        "passed_count": sum(int(b.get("passed_count") or 0) for b in board_results),
        "watchlist_count": sum(int(b.get("watchlist_count") or 0) for b in board_results),
        "rejected_count": sum(int(b.get("rejected_count") or 0) for b in board_results),
    }

    all_passed: list[dict[str, Any]] = []
    all_watchlist: list[dict[str, Any]] = []
    for board in board_results:
        for row in board.get("passed") or []:
            all_passed.append({**row, "board_id": board["id"]})
        for row in board.get("watchlist") or []:
            all_watchlist.append({**row, "board_id": board["id"]})

    payload: dict[str, Any] = {
        "boards_file": str(args.boards_file),
        "search_text": args.search_text or None,
        "fit_check_enabled": args.fit_check,
        "include_weak_proceed": args.include_weak_proceed,
        "limit_per_board": args.limit_per_board,
        "delay_sec": args.delay,
        "backoff_sec": args.backoff,
        "cv_from_passed": args.cv_from_passed,
        "overall": overall,
        "boards": board_results,
        "passed": all_passed,
        "watchlist": all_watchlist if args.include_weak_proceed else [],
    }

    cv_paths: list[str] = []
    if args.cv_from_passed and all_passed:
        written = write_passed_cvs(all_passed, args.cv_out_passed)
        cv_paths = [str(path) for path in written]
        print(f"\npassed CVs: {len(written)} → {args.cv_out_passed}")
        for path in written:
            print(f"  {path}")
    elif args.cv_from_passed:
        print("\npassed CVs: 0 (no passed rows)")

    if args.cv_from_passed:
        payload["cv_out_passed"] = str(args.cv_out_passed)
        payload["cv_passed_count"] = len(cv_paths)
        payload["cv_passed_paths"] = cv_paths

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== overall ===")
    print(
        f"boards ok/error/skipped: "
        f"{overall['boards_ok']}/{overall['boards_error']}/{overall['boards_skipped']}"
    )
    print(
        f"discovered={overall['discovered']} fit_checked={overall['fit_checked']} "
        f"passed={overall['passed_count']} watchlist={overall['watchlist_count']} "
        f"rejected={overall['rejected_count']}"
    )
    print(f"written: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
