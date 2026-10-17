"""Turn a daily multi-board sourcing artifact into a deduped shortlist.

Reads the JSON written by fetch_jobs_multi_board.py (or fetch_jobs_multi_workday.py),
diffs passed/watchlist rows against backend.tracking.state_store (so the same
job is never proposed twice), and writes a human-readable markdown digest of
only the genuinely new rows.

Usage:
  python scripts/build_daily_shortlist.py --artifact out/daily/personio_20260730.json \\
      --run-date 20260730 --out out/daily/shortlist_20260730.md

Every new row (strong pass AND watchlist) also gets its *open topics* —
requirements the JD mentions that domain/cv_master.yaml doesn't yet
(backend/sourcing/open_topics.py). The digest ends with questions to Gabby
so the Master-CV grows where the market asks. Reporting only, no scoring.

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

from backend.sourcing import open_topics  # noqa: E402
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
    labels = row.get("open_topic_labels") or []
    if labels:
        lines.append(f"  - ❓ Offene Themen: {', '.join(labels)}")
    return "\n".join(lines)


def _jd_by_url(rows: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in rows:
        job = row.get("job") or {}
        url = str(row.get("url") or job.get("url") or "")
        text = "\n".join(str(part) for part in (job.get("title") or row.get("title"),
                                                job.get("jd_text")) if part)
        if url and text:
            out[url] = text
    return out


def attach_open_topics(
    new_rows: list[dict[str, Any]],
    jd_texts: dict[str, str],
    *,
    run_date: str,
    backlog_path: Path | None = None,
) -> list[tuple[open_topics.Topic, int]]:
    """Annotate new rows with open topics; update the backlog.

    Returns today's (topic, job count) pairs, most frequent first, excluding
    topics already answered or marked no_experience.
    """
    backlog = open_topics.load_backlog(backlog_path)
    today: dict[str, tuple[open_topics.Topic, int]] = {}
    for row in new_rows:
        jd = jd_texts.get(row.get("url") or "")
        if not jd:
            continue
        topics = [
            t for t in open_topics.find_open_topics(jd)
            if not open_topics.is_suppressed(t.id, backlog)
        ]
        row["open_topics"] = [t.id for t in topics]
        row["open_topic_labels"] = [t.label for t in topics]
        for topic in topics:
            open_topics.record(backlog, topic, job_id=row["job_id"], run_date=run_date)
            prev = today.get(topic.id)
            today[topic.id] = (topic, (prev[1] if prev else 0) + 1)
    open_topics.save_backlog(backlog, backlog_path)
    return sorted(today.values(), key=lambda item: (-item[1], item[0].id))


def _render_questions(
    ranked: list[tuple[open_topics.Topic, int]], backlog: dict[str, dict[str, Any]]
) -> list[str]:
    if not ranked:
        return []
    lines = [
        "",
        "## Fragen an dich – Master-CV anreichern",
        "",
        "Diese Themen fordern die heutigen Treffer (auch Watchlist), im Master-CV "
        "steht dazu noch nichts. Hast du Erfahrung? Erzähl's im Chat, dann kommt es "
        "mit Beleg in den Master-CV.",
        "",
    ]
    for topic, count in ranked:
        total = int((backlog.get(topic.id) or {}).get("count") or count)
        lines.append(
            f"- **{topic.label}** ({count} Job(s) heute, {total} insgesamt) — "
            f"{topic.question} `{topic.id}`"
        )
    lines += [
        "",
        "Keine Erfahrung damit? `python scripts/open_topics.py none <id>` – "
        "dann frage ich nicht mehr.",
    ]
    return lines


def build_shortlist(
    artifact_path: Path,
    *,
    run_date: str,
    out_path: Path,
    state_path: Path | None = None,
    backlog_path: Path | None = None,
) -> list[dict[str, Any]]:
    if backlog_path is None and state_path is not None:
        # Keep tests / alternate state dirs self-contained.
        backlog_path = state_path.parent / "open_topics.json"
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

    ranked = attach_open_topics(
        new_rows,
        _jd_by_url(passed_rows + watchlist_rows),
        run_date=run_date,
        backlog_path=backlog_path,
    )
    if any(row.get("open_topics") for row in new_rows):
        state = state_store.load_state(state_path)
        for row in new_rows:
            if row["job_id"] in state:
                state[row["job_id"]]["open_topics"] = row.get("open_topics") or []
        state_store.save_state(state, state_path)

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
        lines.extend(_render_questions(ranked, open_topics.load_backlog(backlog_path)))
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
