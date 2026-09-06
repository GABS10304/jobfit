"""Tests for scripts/add_manual_job.py (manual job intake outside the boards)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.tracking import state_store  # noqa: E402
from scripts.add_manual_job import add_manual_job  # noqa: E402
from scripts.prepare_application_draft import build_context  # noqa: E402

STRONG_JD = (
    "Senior AI Product Manager\n\nBerlin, Remote\n\n"
    "Product Discovery, AI-Use-Case-Validierung, datenbasierte Produktentscheidungen, "
    "Pilotkunden-Validierung, DSGVO-konforme AI-Analytics-Prozesse. "
    "Stakeholder-Kommunikation mit Fachbereichen und Management. "
    "Requirements Engineering und experimentelle Validierung von AI-Use-Cases. "
    "B2B SaaS im regulierten Umfeld."
)

WEAK_JD = (
    "Sales Consultant (m/w/d)\n\nMunich\n\n"
    "Kaltakquise, Verkaufsgespräche, Umsatzverantwortung, Vertriebsziele."
)


def test_add_manual_job_tracks_new_row(tmp_path: Path):
    state_path = tmp_path / "jobs_state.json"
    result = add_manual_job(
        url="https://example.com/careers/job/999",
        title=None,
        company="TestBank",
        jd_text=STRONG_JD,
        state_path=state_path,
    )

    assert result["is_new"] is True
    assert result["job_id"]
    assert result["language"] == "de"

    entry = state_store.get_entry(result["job_id"], path=state_path)
    assert entry is not None
    assert entry["company"] == "TestBank"


def test_add_manual_job_source_artifact_is_readable_by_prepare_application_draft(
    tmp_path: Path, monkeypatch
):
    """Regression test: add_manual_job() used to write source_artifact="manual"
    (a literal string, not a file), which scripts/prepare_application_draft.py's
    _find_row() then tried to open as a path and crashed with FileNotFoundError
    — meaning "ja zu <job_id>" never actually worked for a manually-added job.
    build_context() itself hardcodes state_store.get_entry(job_id) with no path
    override, so STATE_PATH is monkeypatched here (rather than passed via
    state_path=) to keep both calls reading the same isolated tmp_path state
    file, with no writes to the real repo's out/ directory.
    """
    state_path = tmp_path / "jobs_state.json"
    monkeypatch.setattr(state_store, "STATE_PATH", state_path)

    result = add_manual_job(
        url="https://example.com/careers/job/999",
        title=None,
        company="TestBank",
        jd_text=STRONG_JD,
        state_path=state_path,
    )

    context = build_context(result["job_id"])
    # jd_text_from_job_dict() prepends the (guessed) title, so this isn't a
    # byte-for-byte match — containment is enough to prove the real jd_text
    # made the round trip through the artifact file, not a placeholder/error.
    assert "AI-Use-Case-Validierung" in context["jd_text"]
    assert "DSGVO-konforme AI-Analytics-Prozesse" in context["jd_text"]
    assert context["url"] == "https://example.com/careers/job/999"


def test_add_manual_job_dedups_on_second_call(tmp_path: Path):
    state_path = tmp_path / "jobs_state.json"
    add_manual_job(
        url="https://example.com/careers/job/999",
        title=None,
        company="TestBank",
        jd_text=STRONG_JD,
        state_path=state_path,
    )
    second = add_manual_job(
        url="https://example.com/careers/job/999",
        title=None,
        company="TestBank",
        jd_text=STRONG_JD,
        state_path=state_path,
    )
    assert second["is_new"] is False


def test_add_manual_job_detects_english_jd(tmp_path: Path):
    state_path = tmp_path / "jobs_state.json"
    result = add_manual_job(
        url="https://example.com/careers/job/1000",
        title="Product Owner - GenAI",
        company="Danske Bank",
        jd_text=(
            "We are looking for an experienced Product Owner to lead our GenAI "
            "team. You will work with engineering and data science."
        ),
        state_path=state_path,
    )
    assert result["language"] == "en"


def test_add_manual_job_rejects_weak_title_prefilter(tmp_path: Path):
    state_path = tmp_path / "jobs_state.json"
    result = add_manual_job(
        url="https://example.com/careers/job/1001",
        title=None,
        company="SalesCo",
        jd_text=WEAK_JD,
        state_path=state_path,
    )
    assert result["bucket"] == "rejected"


def test_add_manual_job_flags_relocation_for_solid_score_outside_preferred(tmp_path: Path):
    state_path = tmp_path / "jobs_state.json"
    # Mirrors the real Danske Bank JD in spirit: strong content signals but a
    # location (Copenhagen, Denmark) outside preferred_locations.
    strong_but_far_jd = (
        "Senior AI Product Manager\n\nCopenhagen, Denmark, Hybrid\n\n"
        "Product Discovery, AI-Use-Case-Validierung, datenbasierte Produktentscheidungen, "
        "Pilotkunden-Validierung, DSGVO-konforme AI-Analytics-Prozesse. "
        "Stakeholder-Kommunikation mit Fachbereichen und Management. "
        "Requirements Engineering und experimentelle Validierung von AI-Use-Cases. "
        "B2B SaaS im regulierten Umfeld."
    )
    result = add_manual_job(
        url="https://example.com/careers/job/2000",
        title=None,
        company="FarAwayCo",
        jd_text=strong_but_far_jd,
        state_path=state_path,
    )
    assert result["location_match"] == "outside_preferred"
    if result["top_score"] and result["top_score"] >= 50:
        assert result["relocation_note"] is not None


def test_guess_title_uses_first_nonblank_line():
    from scripts.add_manual_job import _guess_title

    assert _guess_title("\n\nSenior Product Manager\n\nBerlin") == "Senior Product Manager"
