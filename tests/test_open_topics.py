"""Tests for open topics (JD requirements not yet in the Master-CV)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.sourcing import open_topics as ot

LEXICON = """
topics:
  evals:
    label: Evals
    question: Hast du Evals gebaut?
    phrases: [evals, llm-as-judge]
  figma:
    label: Figma
    phrases: [figma]
  rag:
    label: RAG
    phrases: [rag, vector store]
  sql:
    label: SQL
    phrases: [sql]
"""


@pytest.fixture()
def topics(tmp_path: Path) -> list[ot.Topic]:
    path = tmp_path / "lex.yaml"
    path.write_text(LEXICON, encoding="utf-8")
    return ot.load_lexicon(path)


def test_lexicon_defaults(topics):
    by_id = {t.id: t for t in topics}
    assert by_id["figma"].question == "Hast du Erfahrung mit Figma?"
    assert by_id["evals"].question == "Hast du Evals gebaut?"
    assert by_id["rag"].cv_phrases == by_id["rag"].phrases


def test_direction_is_jd_minus_cv(topics):
    jd = "Du baust Evals und RAG-Pipelines, reviewst Flows in Figma."
    cv = "Hybrid-RAG-Chat mit BigQuery gebaut."
    found = [t.id for t in ot.find_open_topics(jd, topics=topics, cv_text=cv)]
    assert found == ["evals", "figma"]  # rag is in the CV, sql not in the JD


def test_word_boundaries_avoid_false_hits(topics):
    # "drag" must not match "rag", "postgresql" style compounds are not "sql" hits either way
    jd = "Drag-and-drop editor, mysqlish wording"
    assert ot.find_open_topics(jd, topics=topics, cv_text="") == []
    assert [t.id for t in ot.find_open_topics("SQL und RAG", topics=topics, cv_text="")] == [
        "rag", "sql"
    ]


def test_backlog_counts_jobs_once_and_ranks(topics, tmp_path: Path):
    path = tmp_path / "open_topics.json"
    backlog = ot.load_backlog(path)
    evals, figma = topics[0], topics[1]
    ot.record(backlog, evals, job_id="j1", run_date="20261017")
    ot.record(backlog, evals, job_id="j1", run_date="20261017")  # same job → no double count
    ot.record(backlog, evals, job_id="j2", run_date="20261018")
    ot.record(backlog, figma, job_id="j2", run_date="20261018")
    ot.save_backlog(backlog, path)

    loaded = ot.load_backlog(path)
    assert loaded["evals"]["count"] == 2 and loaded["evals"]["jobs"] == ["j1", "j2"]
    assert loaded["evals"]["first_seen"] == "20261017" and loaded["evals"]["last_seen"] == "20261018"
    assert [tid for tid, _ in ot.open_topics_ranked(loaded)] == ["evals", "figma"]


def test_status_suppresses_questions(topics, tmp_path: Path):
    path = tmp_path / "open_topics.json"
    backlog: dict = {}
    ot.record(backlog, topics[1], job_id="j1", run_date="20261017")
    ot.save_backlog(backlog, path)

    ot.set_status("figma", ot.STATUS_NO_EXPERIENCE, path=path)
    assert ot.is_suppressed("figma", ot.load_backlog(path))
    assert ot.open_topics_ranked(ot.load_backlog(path)) == []

    ot.set_status("figma", ot.STATUS_OPEN, path=path)
    assert not ot.is_suppressed("figma", ot.load_backlog(path))

    with pytest.raises(ValueError):
        ot.set_status("figma", "maybe", path=path)


def test_set_status_for_unseen_topic_uses_real_lexicon(tmp_path: Path):
    path = tmp_path / "open_topics.json"
    entry = ot.set_status("evals", ot.STATUS_ANSWERED, note="RIWANEXIS", path=path)
    assert entry["status"] == ot.STATUS_ANSWERED and entry["note"] == "RIWANEXIS"
    with pytest.raises(KeyError):
        ot.set_status("not_a_topic", ot.STATUS_ANSWERED, path=path)


def test_real_lexicon_loads_and_flags_skalar_style_jd():
    topics = ot.load_lexicon()
    assert len(topics) >= 20
    jd = ("Evals aufbauen, Build-vs-Buy entscheiden, Flows in Figma reviewen, "
          "DATEV und ELSTER sind ein Plus.")
    found = {t.id for t in ot.find_open_topics(jd, topics=topics, cv_text="")}
    assert {"evals", "build_vs_buy", "figma", "datev_elster"} <= found


def test_shortlist_reports_open_topics_for_watchlist_rows(tmp_path: Path, monkeypatch):
    from scripts import build_daily_shortlist as bds

    monkeypatch.setattr(ot, "_default_context", lambda: (
        tuple(ot.load_lexicon()), "Hybrid-RAG-Chat, Python, Claude"))

    def row(url, title, jd, score):
        return {"url": url, "title": title, "company": "Skalar", "sourcing_bucket": "watchlist",
                "fit_check": {"status_flag": "proceed", "top_score": score},
                "job": {"title": title, "url": url, "jd_text": jd}}

    artifact = tmp_path / "ashby.json"
    artifact.write_text(json.dumps({
        "passed": [],
        "watchlist": [
            row("https://jobs.ashbyhq.com/skalar/9d2d68c1-ca7b-4052-bda0-d2f6b6fe553e",
                "Senior Product Manager", "Evals, Figma und RAG.", 56),
            row("https://jobs.ashbyhq.com/other/0f0f0f0f-1111-2222-3333-444444444444",
                "AI Product Manager", "Evals sind Pflicht.", 60),
        ],
    }), encoding="utf-8")
    state = tmp_path / "state" / "jobs_state.json"
    out = tmp_path / "shortlist.md"

    new_rows = bds.build_shortlist(artifact, run_date="20261017", out_path=out, state_path=state)

    assert len(new_rows) == 2
    md = out.read_text(encoding="utf-8")
    assert "❓ Offene Themen: Evals / LLM-Evaluation, Figma" in md
    assert "## Fragen an dich" in md
    assert "**Evals / LLM-Evaluation** (2 Job(s) heute, 2 insgesamt)" in md
    assert "RAG" not in md.split("## Fragen an dich")[1]  # RAG is in the CV

    saved_state = json.loads(state.read_text(encoding="utf-8"))
    assert any(e.get("open_topics") == ["evals", "figma"] for e in saved_state.values())
    backlog = json.loads((state.parent / "open_topics.json").read_text(encoding="utf-8"))
    assert backlog["evals"]["count"] == 2

    # Mark figma as "no experience" → next run doesn't ask again.
    ot.set_status("figma", ot.STATUS_NO_EXPERIENCE, path=state.parent / "open_topics.json")
    artifact.write_text(json.dumps({"passed": [], "watchlist": [
        row("https://jobs.ashbyhq.com/third/aaaaaaaa-1111-2222-3333-444444444444",
            "Product Manager", "Figma und Evals.", 50)]}), encoding="utf-8")
    bds.build_shortlist(artifact, run_date="20261018", out_path=out, state_path=state)
    md = out.read_text(encoding="utf-8")
    assert "Figma" not in md and "Evals" in md
