"""Tests for scripts/build_daily_shortlist.py, including the new
--new-ids-out machine-readable output used by
scripts/run_decisions_for_new_jobs.py.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.build_daily_shortlist import append_new_ids, build_shortlist


def _write_artifact(path: Path, *, passed=None, watchlist=None) -> None:
    payload = {"passed": passed or [], "watchlist": watchlist or []}
    path.write_text(json.dumps(payload), encoding="utf-8")


def _row(url: str, title: str, score: int = 80) -> dict:
    return {
        "url": url,
        "title": title,
        "board_id": "testco",
        "fit_check": {"status_flag": "proceed", "top_score": score},
    }


def test_build_shortlist_writes_markdown_and_returns_new_rows(tmp_path: Path):
    artifact = tmp_path / "artifact.json"
    _write_artifact(artifact, passed=[_row("https://x.jobs.personio.de/job/1", "Job One")])
    state_path = tmp_path / "state.json"
    out = tmp_path / "shortlist.md"

    new_rows = build_shortlist(artifact, run_date="20260801", out_path=out, state_path=state_path)

    assert len(new_rows) == 1
    assert out.exists()
    assert "Job One" in out.read_text(encoding="utf-8")


def test_append_new_ids_creates_file(tmp_path: Path):
    ids_path = tmp_path / "ids.json"
    rows = [{"job_id": "1_job-one"}, {"job_id": "2_job-two"}]

    result = append_new_ids(rows, ids_path)

    assert result == ["1_job-one", "2_job-two"]
    assert json.loads(ids_path.read_text(encoding="utf-8")) == ["1_job-one", "2_job-two"]


def test_append_new_ids_merges_across_multiple_sources(tmp_path: Path):
    """Personio, Workday, LinkedIn all write to the same file in one run."""
    ids_path = tmp_path / "ids.json"
    append_new_ids([{"job_id": "1_personio-job"}], ids_path)
    append_new_ids([{"job_id": "2_linkedin-job"}, {"job_id": "3_linkedin-job"}], ids_path)

    result = json.loads(ids_path.read_text(encoding="utf-8"))
    assert result == ["1_personio-job", "2_linkedin-job", "3_linkedin-job"]


def test_append_new_ids_handles_empty_new_rows(tmp_path: Path):
    ids_path = tmp_path / "ids.json"
    append_new_ids([{"job_id": "1_job"}], ids_path)
    result = append_new_ids([], ids_path)
    assert result == ["1_job"]
