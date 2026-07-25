"""Tests for multi-board Workday sourcing runner."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from backend.sourcing.personio import JobListing
from scripts import fetch_jobs_multi_workday as multi

REPO_ROOT = Path(__file__).resolve().parent.parent
BOARDS_YAML = REPO_ROOT / "domain" / "workday_boards.yaml"


def test_load_boards_from_yaml():
    boards = multi.load_boards(BOARDS_YAML)
    assert len(boards) >= 3
    ids = {b["id"] for b in boards}
    assert "ing" in ids
    assert "salesforce" in ids
    assert all(b["url"].startswith("https://") for b in boards)
    assert all("myworkdayjobs.com" in b["url"] for b in boards)


def test_multi_workday_aggregates_and_skips_dead(tmp_path: Path):
    out_path = tmp_path / "multi_workday.json"
    boards = [
        {
            "id": "alive",
            "name": "Alive",
            "url": "https://alive.wd3.myworkdayjobs.com/Careers",
        },
        {
            "id": "dead",
            "name": "Dead",
            "url": "https://dead.wd3.myworkdayjobs.com/Careers",
        },
    ]

    listings = [
        JobListing(
            url="https://alive.wd3.myworkdayjobs.com/Careers/job/Berlin/PM_REQ-1",
            title="Product Manager (m/w/d)",
        ),
        JobListing(
            url="https://alive.wd3.myworkdayjobs.com/Careers/job/Berlin/Eng_REQ-2",
            title="Java Engineer (m/w/d)",
        ),
    ]

    def fake_discover(board_url, *, search_text, limit, use_playwright):
        if "dead" in board_url:
            raise RuntimeError("Workday CXS returned non-JSON (possible WAF/HTML challenge)")
        candidates = [listings[0]]
        rejected = [
            {
                "url": listings[1].url,
                "status": "ok",
                "title": listings[1].title,
                "passes_default_filter": False,
                "watchlist": False,
                "sourcing_bucket": "rejected",
                "reject_reason": "title_prefilter",
            }
        ]
        return listings, candidates, rejected, len(listings)

    def fake_process(url, *, use_playwright, fit_check, listing_title=None):
        return {
            "url": url,
            "status": "ok",
            "title": listing_title,
            "passes_default_filter": False,
            "watchlist": True,
            "sourcing_bucket": "watchlist",
            "reject_reason": "watchlist: weak_score=36<75",
            "job": {"title": listing_title, "url": url},
            "fit_check": {
                "status_flag": "proceed",
                "top_score": 36,
                "top_role_id": "ai_product_manager",
                "passes_default_filter": False,
                "watchlist_eligible": True,
                "watchlist_reason": "weak_score=36<75",
            },
        }

    with (
        patch.object(multi, "load_boards", return_value=boards),
        patch.object(multi, "_discover_with_prefilter", side_effect=fake_discover),
        patch.object(multi, "_process_job", side_effect=fake_process),
        patch.object(multi, "time") as time_mod,
        patch(
            "sys.argv",
            [
                "fetch_jobs_multi_workday.py",
                "--out",
                str(out_path),
                "--delay",
                "0",
                "--backoff",
                "0.01",
            ],
        ),
    ):
        time_mod.sleep = lambda *_a, **_k: None
        code = multi.main()

    assert code == 0
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["search_text"] == "Product Manager"
    assert payload["include_weak_proceed"] is True
    assert payload["overall"]["boards_tried"] == 2
    assert payload["overall"]["boards_ok"] == 1
    assert payload["overall"]["boards_error"] == 1
    assert payload["overall"]["passed_count"] == 0
    assert payload["overall"]["watchlist_count"] == 1
    assert payload["watchlist"][0]["board_id"] == "alive"
    dead = next(b for b in payload["boards"] if b["id"] == "dead")
    assert dead["status"] == "error"


def test_include_weak_proceed_default_on():
    rows = [
        {
            "url": "u1",
            "passes_default_filter": False,
            "watchlist": True,
        }
    ]
    passed, watchlist, rejected = multi._bucket_rows(rows, include_weak_proceed=True)
    assert passed == []
    assert len(watchlist) == 1
    assert rejected == []
    _, watchlist_off, rejected_off = multi._bucket_rows(
        rows, include_weak_proceed=False
    )
    assert watchlist_off == []
    assert len(rejected_off) == 1
    assert "include-weak-proceed" in (multi.__doc__ or "")
    assert "Product Manager" in (multi.__doc__ or "")
