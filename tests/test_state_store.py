"""Tests for backend.tracking.state_store (daily dedup + approval status)."""

import pytest

from backend.tracking import state_store


def _row(url, title, board_id="testco", score=80, status_flag="proceed"):
    return {
        "url": url,
        "title": title,
        "board_id": board_id,
        "fit_check": {"status_flag": status_flag, "top_score": score},
    }


def test_make_job_id_uses_numeric_id_when_present():
    job_id = state_store.make_job_id(
        url="https://x.jobs.personio.de/job/123", title="Senior Product Manager"
    )
    assert job_id == "123_senior-product-manager"


def test_make_job_id_falls_back_to_slug_without_numeric_id():
    job_id = state_store.make_job_id(url="https://x.example/careers/foo", title="AI PM")
    assert job_id == "ai-pm"


def test_upsert_and_diff_first_run_returns_all_as_new(tmp_path):
    state_path = tmp_path / "jobs_state.json"
    rows = [_row("https://x.jobs.personio.de/job/1", "Job One")]
    new_rows = state_store.upsert_and_diff(
        rows,
        source_artifact="artifact.json",
        run_date="20260730",
        sourcing_bucket="passed",
        path=state_path,
    )
    assert len(new_rows) == 1
    assert new_rows[0]["status"] == state_store.STATUS_PROPOSED
    assert new_rows[0]["first_seen"] == "20260730"


def test_upsert_and_diff_second_run_dedups(tmp_path):
    state_path = tmp_path / "jobs_state.json"
    rows = [_row("https://x.jobs.personio.de/job/1", "Job One")]
    state_store.upsert_and_diff(
        rows,
        source_artifact="artifact.json",
        run_date="20260730",
        sourcing_bucket="passed",
        path=state_path,
    )
    new_rows_second = state_store.upsert_and_diff(
        rows,
        source_artifact="artifact2.json",
        run_date="20260731",
        sourcing_bucket="passed",
        path=state_path,
    )
    assert new_rows_second == []
    state = state_store.load_state(state_path)
    job_id = state_store.make_job_id(url=rows[0]["url"], title=rows[0]["title"])
    assert state[job_id]["last_seen"] == "20260731"
    assert state[job_id]["first_seen"] == "20260730"


def test_upsert_and_diff_new_job_alongside_seen_job(tmp_path):
    state_path = tmp_path / "jobs_state.json"
    seen = [_row("https://x.jobs.personio.de/job/1", "Job One")]
    state_store.upsert_and_diff(
        seen,
        source_artifact="a.json",
        run_date="20260730",
        sourcing_bucket="passed",
        path=state_path,
    )
    mixed = seen + [_row("https://x.jobs.personio.de/job/2", "Job Two")]
    new_rows = state_store.upsert_and_diff(
        mixed,
        source_artifact="b.json",
        run_date="20260731",
        sourcing_bucket="passed",
        path=state_path,
    )
    assert len(new_rows) == 1
    assert new_rows[0]["title"] == "Job Two"


def test_mark_status_updates_and_validates(tmp_path):
    state_path = tmp_path / "jobs_state.json"
    rows = [_row("https://x.jobs.personio.de/job/1", "Job One")]
    state_store.upsert_and_diff(
        rows,
        source_artifact="a.json",
        run_date="20260730",
        sourcing_bucket="passed",
        path=state_path,
    )
    job_id = state_store.make_job_id(url=rows[0]["url"], title=rows[0]["title"])

    updated = state_store.mark_status(job_id, state_store.STATUS_APPROVED, path=state_path)
    assert updated["status"] == state_store.STATUS_APPROVED
    assert state_store.get_entry(job_id, path=state_path)["status"] == state_store.STATUS_APPROVED

    with pytest.raises(ValueError):
        state_store.mark_status(job_id, "not_a_real_status", path=state_path)

    with pytest.raises(KeyError):
        state_store.mark_status("does-not-exist", state_store.STATUS_APPROVED, path=state_path)


def test_mark_sent_sets_status_and_sent_at(tmp_path):
    state_path = tmp_path / "jobs_state.json"
    rows = [_row("https://x.jobs.personio.de/job/1", "Job One")]
    state_store.upsert_and_diff(
        rows,
        source_artifact="a.json",
        run_date="20260730",
        sourcing_bucket="passed",
        path=state_path,
    )
    job_id = state_store.make_job_id(url=rows[0]["url"], title=rows[0]["title"])
    state_store.mark_status(job_id, state_store.STATUS_FINALIZED, path=state_path)

    updated = state_store.mark_sent(job_id, sent_date="20260731", path=state_path)
    assert updated["status"] == state_store.STATUS_SENT
    assert updated["sent_at"] == "20260731"
    assert state_store.get_entry(job_id, path=state_path)["status"] == state_store.STATUS_SENT


def test_mark_sent_defaults_sent_at_to_today(tmp_path):
    state_path = tmp_path / "jobs_state.json"
    rows = [_row("https://x.jobs.personio.de/job/1", "Job One")]
    state_store.upsert_and_diff(
        rows,
        source_artifact="a.json",
        run_date="20260730",
        sourcing_bucket="passed",
        path=state_path,
    )
    job_id = state_store.make_job_id(url=rows[0]["url"], title=rows[0]["title"])

    updated = state_store.mark_sent(job_id, path=state_path)
    assert updated["status"] == state_store.STATUS_SENT
    assert len(updated["sent_at"]) == 8  # YYYYMMDD


def test_mark_sent_unknown_job_id_raises(tmp_path):
    state_path = tmp_path / "jobs_state.json"
    with pytest.raises(KeyError):
        state_store.mark_sent("does-not-exist", path=state_path)


def test_get_by_status_filters(tmp_path):
    state_path = tmp_path / "jobs_state.json"
    rows = [
        _row("https://x.jobs.personio.de/job/1", "Job One"),
        _row("https://x.jobs.personio.de/job/2", "Job Two"),
    ]
    state_store.upsert_and_diff(
        rows,
        source_artifact="a.json",
        run_date="20260730",
        sourcing_bucket="passed",
        path=state_path,
    )
    job_id_1 = state_store.make_job_id(url=rows[0]["url"], title=rows[0]["title"])
    state_store.mark_status(job_id_1, state_store.STATUS_FINALIZED, path=state_path)

    proposed = state_store.get_by_status(state_store.STATUS_PROPOSED, path=state_path)
    finalized = state_store.get_by_status(state_store.STATUS_FINALIZED, path=state_path)
    assert len(proposed) == 1
    assert len(finalized) == 1
    assert finalized[0]["job_id"] == job_id_1
