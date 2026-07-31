"""Cross-run job state (Phase 4) – dedup for the daily shortlist + approval status.

JSON file at ``out/tracking/jobs_state.json``, keyed by a stable job_id derived
from url/title (reuses the same slugging as backend/generation/watchlist_cv.py
so ids match what shows up in filenames elsewhere in the pipeline).

Status lifecycle: new -> proposed -> approved -> draft_ready -> finalized -> sent
(+ rejected, set by the user declining a proposed job).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.generation.watchlist_cv import job_id_from_url, slugify_title

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_PATH = REPO_ROOT / "out" / "tracking" / "jobs_state.json"

STATUS_NEW = "new"
STATUS_PROPOSED = "proposed"
STATUS_APPROVED = "approved"
STATUS_DRAFT_READY = "draft_ready"
STATUS_FINALIZED = "finalized"
STATUS_SENT = "sent"
STATUS_REJECTED = "rejected"

_VALID_STATUSES = frozenset(
    {
        STATUS_NEW,
        STATUS_PROPOSED,
        STATUS_APPROVED,
        STATUS_DRAFT_READY,
        STATUS_FINALIZED,
        STATUS_SENT,
        STATUS_REJECTED,
    }
)


def make_job_id(*, url: str | None, title: str | None) -> str:
    """Stable id for a job row: numeric board-job-id when parseable, else slug."""
    numeric = job_id_from_url(url)
    slug = slugify_title(title)
    return f"{numeric}_{slug}" if numeric else slug


def load_state(path: Path | None = None) -> dict[str, dict[str, Any]]:
    target = path or STATE_PATH
    if not target.exists():
        return {}
    with target.open(encoding="utf-8") as f:
        raw = json.load(f) or {}
    return raw if isinstance(raw, dict) else {}


def save_state(state: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    target = path or STATE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
    return target


def get_entry(job_id: str, path: Path | None = None) -> dict[str, Any] | None:
    return load_state(path).get(job_id)


def get_by_status(status: str, path: Path | None = None) -> list[dict[str, Any]]:
    return [entry for entry in load_state(path).values() if entry.get("status") == status]


def mark_status(job_id: str, status: str, path: Path | None = None) -> dict[str, Any]:
    if status not in _VALID_STATUSES:
        raise ValueError(f"Unknown status {status!r}; expected one of {sorted(_VALID_STATUSES)}")
    state = load_state(path)
    if job_id not in state:
        raise KeyError(f"Unknown job_id: {job_id}")
    state[job_id]["status"] = status
    save_state(state, path)
    return state[job_id]


def mark_sent(
    job_id: str, *, sent_date: str | None = None, path: Path | None = None
) -> dict[str, Any]:
    """Mark an application as actually submitted; records ``sent_at`` (YYYYMMDD).

    Gabriel submits applications himself (no auto-apply) — this just records
    that it happened, for tracking/history. Callable regardless of current
    status; typically follows ``finalized``.
    """
    state = load_state(path)
    if job_id not in state:
        raise KeyError(f"Unknown job_id: {job_id}")
    state[job_id]["status"] = STATUS_SENT
    state[job_id]["sent_at"] = sent_date or datetime.now(timezone.utc).strftime("%Y%m%d")
    save_state(state, path)
    return state[job_id]


def upsert_and_diff(
    rows: list[dict[str, Any]],
    *,
    source_artifact: str,
    run_date: str,
    sourcing_bucket: str,
    path: Path | None = None,
) -> list[dict[str, Any]]:
    """Merge sourcing rows into the state store; return only genuinely new ones.

    A "new" row is one whose job_id was never seen before (any status). Rows
    already tracked (regardless of status) are not re-proposed — only their
    ``last_seen`` is refreshed. Newly-added rows are stored with status
    STATUS_PROPOSED (the daily run's job is to propose, not decide).
    """
    state = load_state(path)
    new_rows: list[dict[str, Any]] = []

    for row in rows:
        job = row.get("job") or {}
        url = str(row.get("url") or job.get("url") or "")
        title = str(row.get("title") or job.get("title") or "")
        job_id = make_job_id(url=url, title=title)
        fit = row.get("fit_check") or {}

        if job_id in state:
            state[job_id]["last_seen"] = run_date
            continue

        entry = {
            "job_id": job_id,
            "url": url,
            "title": title,
            "company": row.get("board_id") or row.get("company"),
            "status_flag": fit.get("status_flag"),
            "top_score": fit.get("top_score"),
            "sourcing_bucket": sourcing_bucket,
            "source_artifact": source_artifact,
            "status": STATUS_PROPOSED,
            "first_seen": run_date,
            "last_seen": run_date,
        }
        state[job_id] = entry
        new_rows.append(entry)

    save_state(state, path)
    return new_rows
