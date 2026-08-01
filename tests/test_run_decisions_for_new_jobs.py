"""Tests for scripts/run_decisions_for_new_jobs.py's fail-open batch runner."""

from __future__ import annotations

from scripts.run_decisions_for_new_jobs import run_decisions


def _fake_decision(decision: str, action: str = "draft_application") -> dict:
    return {
        "advocate": {"case_for_pursuing": "x", "key_strengths": ["x"], "excitement_level": "high"},
        "skeptic": {
            "case_against_pursuing": "x",
            "key_risks": ["x"],
            "red_flags": [],
            "concern_level": "low",
        },
        "decision": {
            "decision": decision,
            "recommended_action": action,
            "reasoning": "x",
            "confidence": "medium",
        },
    }


def test_run_decisions_counts_pursue_recommendations():
    def decide(job_id: str) -> dict:
        return _fake_decision("pursue" if job_id != "2_skip-me" else "skip")

    summary = run_decisions(["1_job", "2_skip-me", "3_job"], decide=decide)

    assert summary["pursue_count"] == 2
    assert summary["skipped_agent_errors"] == 0
    assert set(summary["results"]) == {"1_job", "2_skip-me", "3_job"}


def test_run_decisions_fails_open_on_per_job_errors():
    def decide(job_id: str) -> dict:
        if job_id == "2_broken":
            raise RuntimeError("no API key configured")
        return _fake_decision("pursue")

    summary = run_decisions(["1_job", "2_broken", "3_job"], decide=decide)

    assert summary["pursue_count"] == 2
    assert summary["skipped_agent_errors"] == 1
    assert "2_broken" not in summary["results"]
    assert "1_job" in summary["results"] and "3_job" in summary["results"]


def test_run_decisions_handles_all_jobs_failing():
    def decide(job_id: str) -> dict:
        raise RuntimeError("no credentials")

    summary = run_decisions(["1_job", "2_job"], decide=decide)

    assert summary["pursue_count"] == 0
    assert summary["skipped_agent_errors"] == 2
    assert summary["results"] == {}


def test_run_decisions_empty_list():
    summary = run_decisions([], decide=lambda job_id: _fake_decision("pursue"))
    assert summary == {"results": {}, "pursue_count": 0, "skipped_agent_errors": 0}
