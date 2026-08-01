"""Turn a daily multi-board sourcing artifact into a deduped shortlist.

Reads the JSON written by fetch_jobs_multi_board.py (or fetch_jobs_multi_workday.py),
diffs passed/watchlist rows against backend.tracking.state_store (so the same
job is never proposed twice), and writes a human-readable markdown digest of
only the genuinely new rows.

Usage:
  python scripts/build_daily_shortlist.py --artifact out/daily/personio_20260730.json \\
      --run-date 20260730 --out out/daily/shortlist_20260730.md

Prints "NEW_COUNT=<n>" on the last line so callers (daily_sourcing_run.sh) can
decide whether to fire a notification, without parsing markdown.
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

from backend.sourcing.filtering import relocation_note  # noqa: E402
from backend.tracking import state_store  # noqa: E402


def _render_row(row: dict[str, Any]) -> str:
    bucket_label = "STRONG-PASS" if row["sourcing_bucket"] == "passed" else "watchlist"
    score = row.get("top_score")
    score_text = str(score) if score is not None else "n/a"
    company = row.get("company") or "?"
    lines = [
        f"- **{row['title']}** @ {company} — {bucket_label}, Score {score_text}",
        f"  - job_id: `{row['job_id']}`",
        f"  - {row['url']}",
    ]
    note = relocation_note(score, row.get("location_match"))
    if note:
        lines.append(f"  - 📍 {note}")
    return "\n".join(lines)


def build_shortlist(
    artifact_path: Path,
    *,
    run_date: str,
    out_path: Path,
    state_path: Path | None = None,
) -> list[dict[str, Any]]:
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    passed_rows = payload.get("passed") or []
    watchlist_rows = payload.get("watchlist") or []

    new_passed = state_store.upsert_and_diff(
        passed_rows,
        source_artifact=str(artifact_path),
        run_date=run_date,
        sourcing_bucket="passed",
        path=state_path,
    )
    new_watchlist = state_store.upsert_and_diff(
        watchlist_rows,
        source_artifact=str(artifact_path),
        run_date=run_date,
        sourcing_bucket="watchlist",
        path=state_path,
    )
    new_rows = new_passed + new_watchlist

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if new_rows:
        lines = [
            f"# Neue Job-Vorschläge — {run_date}",
            "",
            f"{len(new_rows)} neue Treffer ({len(new_passed)} Strong-Pass, "
            f"{len(new_watchlist)} Watchlist). Sag im Chat \"ja zu <job_id>\" für einen Entwurf.",
            "",
        ]
        lines.extend(_render_row(row) for row in new_rows)
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        out_path.write_text(
            f"# Neue Job-Vorschläge — {run_date}\n\nKeine neuen Treffer heute.\n",
            encoding="utf-8",
        )

    return new_rows


def append_new_ids(new_rows: list[dict[str, Any]], ids_path: Path) -> list[str]:
    """Append new job_ids to a JSON list file, creating/merging as needed.

    Multiple sources in one daily run (Personio, Workday, LinkedIn) share
    one file, so a later call must not clobber an earlier one's ids.
    """
    existing: list[str] = []
    if ids_path.exists():
        existing = json.loads(ids_path.read_text(encoding="utf-8"))
    combined = existing + [row["job_id"] for row in new_rows]
    ids_path.parent.mkdir(parents=True, exist_ok=True)
    ids_path.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
    return combined


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--run-date", required=True, help="YYYYMMDD, used for dedup + filenames")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--new-ids-out",
        type=Path,
        default=None,
        help="Optional: write the new job_ids as a JSON list (machine-readable, "
        "for scripts/run_decisions_for_new_jobs.py). Appends if the file already "
        "exists (multiple sources in one daily run share one list).",
    )
    args = parser.parse_args()

    if not args.artifact.exists():
        print(f"artifact not found: {args.artifact}", file=sys.stderr)
        return 1

    new_rows = build_shortlist(args.artifact, run_date=args.run_date, out_path=args.out)
    print(f"shortlist written: {args.out}")
    print(f"NEW_COUNT={len(new_rows)}")

    if args.new_ids_out is not None:
        append_new_ids(new_rows, args.new_ids_out)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
