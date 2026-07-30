"""Tests for the approval-driven scripts: prepare_application_draft + finalize_application."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
from pypdf import PdfReader

from backend.tracking import state_store
from scripts import finalize_application, prepare_application_draft

JD_TEXT = (
    "AI Product Manager (m/w/d)\n\n"
    "Remote\n\n"
    "Wir suchen jemanden mit Erfahrung in Product Discovery, "
    "stakeholder communication und data driven decision making im B2B SaaS Umfeld."
)


def _write_artifact(tmp_path: Path) -> Path:
    artifact = {
        "passed": [
            {
                "url": "https://example.jobs.personio.de/job/999",
                "title": "AI Product Manager (m/w/d)",
                "board_id": "example",
                "job": {
                    "title": "AI Product Manager (m/w/d)",
                    "jd_text": JD_TEXT,
                    "url": "https://example.jobs.personio.de/job/999",
                    "location": "Remote",
                    "work_mode": "Remote",
                    "employment_type": "Vollzeit",
                    "source": "personio",
                    "fetched_at": "2026-07-30T00:00:00+00:00",
                },
                "fit_check": {"status_flag": "proceed", "top_score": 80},
            }
        ],
        "watchlist": [],
    }
    path = tmp_path / "personio_20260730.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    return path


def _seed_state(tmp_path: Path, artifact_path: Path) -> tuple[Path, str]:
    state_path = tmp_path / "jobs_state.json"
    rows = [
        {
            "url": "https://example.jobs.personio.de/job/999",
            "title": "AI Product Manager (m/w/d)",
            "board_id": "example",
            "fit_check": {"status_flag": "proceed", "top_score": 80},
        }
    ]
    state_store.upsert_and_diff(
        rows,
        source_artifact=str(artifact_path),
        run_date="20260730",
        sourcing_bucket="passed",
        path=state_path,
    )
    job_id = state_store.make_job_id(url=rows[0]["url"], title=rows[0]["title"])
    return state_path, job_id


def test_build_draft_writes_cv_and_context(tmp_path, monkeypatch):
    artifact_path = _write_artifact(tmp_path)
    state_path, job_id = _seed_state(tmp_path, artifact_path)
    monkeypatch.setattr(state_store, "STATE_PATH", state_path)

    review_dir = tmp_path / "review"
    out_dir = prepare_application_draft.build_draft(job_id, review_dir=review_dir)

    assert (out_dir / "cv.md").is_file()
    assert (out_dir / "cv.pdf").is_file()
    context = json.loads((out_dir / "context.json").read_text(encoding="utf-8"))
    assert context["job_id"] == job_id
    assert "Product Discovery" in context["jd_text"] or "product discovery" in context["jd_text"].casefold()
    assert context["role_id"]

    entry = state_store.get_entry(job_id, path=state_path)
    assert entry["status"] == state_store.STATUS_DRAFT_READY


def test_build_draft_unknown_job_id_raises(tmp_path, monkeypatch):
    state_path = tmp_path / "jobs_state.json"
    state_store.save_state({}, state_path)
    monkeypatch.setattr(state_store, "STATE_PATH", state_path)

    with pytest.raises(KeyError):
        prepare_application_draft.build_draft("does-not-exist", review_dir=tmp_path / "review")


def test_finalize_requires_anschreiben_first(tmp_path, monkeypatch):
    artifact_path = _write_artifact(tmp_path)
    state_path, job_id = _seed_state(tmp_path, artifact_path)
    monkeypatch.setattr(state_store, "STATE_PATH", state_path)

    review_dir = tmp_path / "review"
    prepare_application_draft.build_draft(job_id, review_dir=review_dir)

    with pytest.raises(FileNotFoundError):
        finalize_application.finalize(
            job_id, review_dir=review_dir, applications_dir=tmp_path / "applications_ready"
        )


def test_finalize_writes_combined_pdf_and_marks_finalized(tmp_path, monkeypatch):
    artifact_path = _write_artifact(tmp_path)
    state_path, job_id = _seed_state(tmp_path, artifact_path)
    monkeypatch.setattr(state_store, "STATE_PATH", state_path)

    review_dir = tmp_path / "review"
    out_dir = prepare_application_draft.build_draft(job_id, review_dir=review_dir)
    (out_dir / "anschreiben.md").write_text(
        "Sehr geehrte Damen und Herren,\n\nTestanschreiben.\n\nMit freundlichen Grüßen\n",
        encoding="utf-8",
    )

    applications_dir = tmp_path / "applications_ready"
    pdf_path = finalize_application.finalize(
        job_id, review_dir=review_dir, applications_dir=applications_dir
    )

    assert pdf_path.is_file()
    reader = PdfReader(str(pdf_path))
    assert len(reader.pages) >= 2
    assert "Testanschreiben" in (reader.pages[0].extract_text() or "")

    entry = state_store.get_entry(job_id, path=state_path)
    assert entry["status"] == state_store.STATUS_FINALIZED
