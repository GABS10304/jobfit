"""Tests for watchlist → CV variant path (weak-match labeled)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.generation.watchlist_cv import (
    WEAK_MATCH_LABEL,
    jd_text_from_job_dict,
    prepend_weak_match_note,
    watchlist_cv_filename,
    write_watchlist_cv_from_row,
    write_watchlist_cvs,
)
from backend.sourcing.personio import parse_personio_html

REPO_ROOT = Path(__file__).resolve().parent.parent
JOB_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "personio_flex_ai_pm.html"
FLEX_JOB_URL = "https://flex-capital-management-gmbh.jobs.personio.de/job/2689046?language=de"


@pytest.fixture
def flex_watchlist_row() -> dict:
    html = JOB_FIXTURE.read_text(encoding="utf-8")
    job = parse_personio_html(html, FLEX_JOB_URL)
    return {
        "url": FLEX_JOB_URL,
        "status": "ok",
        "title": job.title,
        "passes_default_filter": False,
        "watchlist": True,
        "sourcing_bucket": "watchlist",
        "reject_reason": "watchlist: weak_score=32<75",
        "job": job.to_dict(),
        "fit_check": {
            "status_flag": "proceed",
            "top_score": 32,
            "top_role_id": "technical_product_manager",
            "passes_default_filter": False,
            "watchlist_eligible": True,
            "watchlist_reason": "weak_score=32<75",
        },
    }


def test_watchlist_cv_filename_labeled_weak_match():
    name = watchlist_cv_filename(
        title="AI Product Manager (m/w/d)",
        url=FLEX_JOB_URL,
        top_score=32,
    )
    assert name.startswith(f"{WEAK_MATCH_LABEL}_")
    assert "score32" in name
    assert "2689046" in name
    assert name.endswith(".md")
    assert "passed" not in name


def test_prepend_weak_match_note():
    text = prepend_weak_match_note(
        "# Name\n\n## Profil\n",
        title="AI PM",
        top_score=32,
        watchlist_reason="weak_score=32<75",
    )
    assert "Weak-Match / Watchlist" in text
    assert WEAK_MATCH_LABEL in text
    assert "32" in text
    assert text.index("Weak-Match") < text.index("# Name")


def test_write_watchlist_cv_from_row_writes_file(flex_watchlist_row: dict, tmp_path: Path):
    """Mock selection input path: render_watchlist_cv → file on disk."""
    fake_md = "# Gabriel\n\n## Profil\nAusrichtung: TPM.\n"
    with patch(
        "backend.generation.watchlist_cv.render_watchlist_cv",
        return_value=prepend_weak_match_note(
            fake_md,
            title=flex_watchlist_row["title"],
            top_score=32,
            watchlist_reason="weak_score=32<75",
        ),
    ) as render_mock:
        path = write_watchlist_cv_from_row(flex_watchlist_row, tmp_path)

    assert path.is_file()
    assert path.parent == tmp_path
    assert WEAK_MATCH_LABEL in path.name
    content = path.read_text(encoding="utf-8")
    assert "Weak-Match / Watchlist" in content
    assert "# Gabriel" in content
    render_mock.assert_called_once()
    call_kwargs = render_mock.call_args.kwargs
    assert "AI Product Manager" in (call_kwargs.get("title") or "")
    assert call_kwargs.get("top_score") == 32
    assert "AI Product Manager" in call_kwargs["jd_text"] or "AI-Projekte" in call_kwargs[
        "jd_text"
    ]


def test_write_watchlist_cvs_batch(flex_watchlist_row: dict, tmp_path: Path):
    with patch(
        "backend.generation.watchlist_cv.render_watchlist_cv",
        return_value=prepend_weak_match_note("# CV\n", top_score=32),
    ):
        paths = write_watchlist_cvs([flex_watchlist_row], tmp_path)

    assert len(paths) == 1
    assert paths[0].is_file()


def test_passed_cv_filename_labeled_passed():
    from backend.generation.watchlist_cv import PASSED_MATCH_LABEL, passed_cv_filename

    name = passed_cv_filename(
        title="AI Product Manager (m/w/d)",
        url=FLEX_JOB_URL,
        top_score=76,
    )
    assert name.startswith(f"{PASSED_MATCH_LABEL}_")
    assert "score76" in name
    assert "2689046" in name
    assert WEAK_MATCH_LABEL not in name


def test_write_passed_cv_from_row(flex_watchlist_row: dict, tmp_path: Path):
    from backend.generation.watchlist_cv import (
        PASSED_MATCH_LABEL,
        prepend_passed_note,
        write_passed_cv_from_row,
    )

    row = {
        **flex_watchlist_row,
        "passes_default_filter": True,
        "watchlist": False,
        "sourcing_bucket": "passed",
        "reject_reason": None,
        "fit_check": {
            **flex_watchlist_row["fit_check"],
            "top_score": 76,
            "passes_default_filter": True,
            "watchlist_eligible": False,
            "watchlist_reason": None,
        },
    }
    with patch(
        "backend.generation.watchlist_cv.render_passed_cv",
        return_value=prepend_passed_note("# CV\n", title=row["title"], top_score=76),
    ):
        path = write_passed_cv_from_row(row, tmp_path)

    assert path.is_file()
    assert PASSED_MATCH_LABEL in path.name
    assert "Strong-Pass" in path.read_text(encoding="utf-8")


def test_batch_cv_from_watchlist_flag(tmp_path: Path):
    """CLI --cv-from-watchlist writes CV paths into batch JSON (mocked pipeline)."""
    from backend.sourcing.personio import extract_job_listings_from_html
    from scripts import fetch_jobs_batch as batch

    board_html = (
        REPO_ROOT / "tests" / "fixtures" / "personio_flex_board.html"
    ).read_text(encoding="utf-8")
    board_url = "https://flex-capital-management-gmbh.jobs.personio.de/?language=de"
    listings = extract_job_listings_from_html(board_html, board_url)
    listings = [item for item in listings if item.title and "AI Product Manager" in item.title]
    out_path = tmp_path / "batch.json"
    cv_out = tmp_path / "cv_watchlist"

    html = JOB_FIXTURE.read_text(encoding="utf-8")
    job = parse_personio_html(html, FLEX_JOB_URL)

    def fake_process(url, *, use_playwright, fit_check, listing_title=None):
        return {
            "url": url,
            "status": "ok",
            "title": listing_title,
            "passes_default_filter": False,
            "watchlist": True,
            "sourcing_bucket": "watchlist",
            "reject_reason": "watchlist: weak_score=32<75",
            "job": job.to_dict(),
            "fit_check": {
                "status_flag": "proceed",
                "top_score": 32,
                "top_role_id": "technical_product_manager",
                "passes_default_filter": False,
                "watchlist_eligible": True,
                "watchlist_reason": "weak_score=32<75",
            },
        }

    with (
        patch.object(batch, "discover_job_listings", return_value=listings),
        patch.object(batch, "_process_job", side_effect=fake_process),
        patch(
            "backend.generation.watchlist_cv.render_watchlist_cv",
            return_value=prepend_weak_match_note("# CV\n", top_score=32),
        ),
        patch(
            "sys.argv",
            [
                "fetch_jobs_batch.py",
                "--board-url",
                board_url,
                "--include-weak-proceed",
                "--cv-from-watchlist",
                "--cv-out",
                str(cv_out),
                "--out",
                str(out_path),
            ],
        ),
    ):
        code = batch.main()

    assert code == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["cv_from_watchlist"] is True
    assert payload["include_weak_proceed"] is True
    assert payload["cv_watchlist_count"] == 1
    assert payload["passed_count"] == 0
    assert len(payload["cv_watchlist_paths"]) == 1
    written = Path(payload["cv_watchlist_paths"][0])
    assert written.is_file()
    assert WEAK_MATCH_LABEL in written.name
    assert "Weak-Match" in written.read_text(encoding="utf-8")
    # Cached _fit must not leak into JSON
    assert "_fit" not in payload["watchlist"][0]
