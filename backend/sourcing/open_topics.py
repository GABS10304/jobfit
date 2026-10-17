"""Open topics: what a JD asks for that the Master-CV doesn't mention yet.

Direction matters. The V3 fit-check's ``missing_signals`` are *profile*
signals the JD doesn't contain (e.g. "govtech" missing from a tax-startup
JD) — useless as questions. This module goes the other way:

    JD mentions topic  AND  cv_master doesn't  →  ask Gabby

Every sourcing hit (strong pass and watchlist) gets its open topics, the
daily shortlist turns them into questions, and the answers enrich the
Master-CV. Rule from the Skalar case (Okt 2026): "no evidence in the CV" is
a question, not a gap.

Pure reporting layer: nothing here feeds V3 scoring (V3-Freeze).

Backlog file: ``out/tracking/open_topics.json``
  topic_id -> {label, status: open|answered|no_experience, count,
               first_seen, last_seen, jobs: [last job_ids]}
``answered`` / ``no_experience`` topics are never asked again;
``answered`` normally also shows up in the CV next run, which suppresses it
anyway.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LEXICON_PATH = REPO_ROOT / "domain" / "open_topics_lexicon.yaml"
CV_PATHS = (REPO_ROOT / "domain" / "cv_master.yaml", REPO_ROOT / "domain" / "Master-CV-structured.md")
BACKLOG_PATH = REPO_ROOT / "out" / "tracking" / "open_topics.json"

STATUS_OPEN = "open"
STATUS_ANSWERED = "answered"
STATUS_NO_EXPERIENCE = "no_experience"
VALID_STATUSES = frozenset({STATUS_OPEN, STATUS_ANSWERED, STATUS_NO_EXPERIENCE})
MAX_JOBS_PER_TOPIC = 10
_WORD = "a-z0-9äöüß"


@dataclass(frozen=True)
class Topic:
    id: str
    label: str
    question: str
    phrases: tuple[str, ...]
    cv_phrases: tuple[str, ...]


def _phrase_re(phrase: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![{_WORD}]){re.escape(phrase.casefold())}(?![{_WORD}])")


def _contains_any(text_cf: str, phrases: Iterable[str]) -> bool:
    return any(_phrase_re(p).search(text_cf) for p in phrases if p.strip())


def load_lexicon(path: Path | None = None) -> list[Topic]:
    raw = yaml.safe_load((path or LEXICON_PATH).read_text(encoding="utf-8")) or {}
    topics: list[Topic] = []
    for topic_id, spec in (raw.get("topics") or {}).items():
        if not isinstance(spec, dict):
            continue
        phrases = tuple(str(p) for p in spec.get("phrases") or [] if str(p).strip())
        if not phrases:
            continue
        label = str(spec.get("label") or topic_id)
        topics.append(
            Topic(
                id=str(topic_id),
                label=label,
                question=str(spec.get("question") or f"Hast du Erfahrung mit {label}?"),
                phrases=phrases,
                cv_phrases=tuple(str(p) for p in spec.get("cv_phrases") or phrases),
            )
        )
    return topics


def load_cv_text(paths: Iterable[Path] = CV_PATHS) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in paths if p.exists()).casefold()


@lru_cache(maxsize=1)
def _default_context() -> tuple[tuple[Topic, ...], str]:
    return tuple(load_lexicon()), load_cv_text()


def find_open_topics(
    jd_text: str,
    *,
    topics: Iterable[Topic] | None = None,
    cv_text: str | None = None,
) -> list[Topic]:
    """Topics the JD mentions that the CV doesn't, in lexicon order."""
    if topics is None or cv_text is None:
        default_topics, default_cv = _default_context()
        topics = default_topics if topics is None else topics
        cv_text = default_cv if cv_text is None else cv_text
    jd_cf = (jd_text or "").casefold()
    cv_cf = cv_text.casefold()
    return [
        topic
        for topic in topics
        if _contains_any(jd_cf, topic.phrases) and not _contains_any(cv_cf, topic.cv_phrases)
    ]


# ----------------------------------------------------------------- backlog


def load_backlog(path: Path | None = None) -> dict[str, dict[str, Any]]:
    target = path or BACKLOG_PATH
    if not target.exists():
        return {}
    try:
        raw = json.loads(target.read_text(encoding="utf-8")) or {}
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def save_backlog(backlog: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    target = path or BACKLOG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(backlog, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return target


def is_suppressed(topic_id: str, backlog: dict[str, dict[str, Any]]) -> bool:
    return (backlog.get(topic_id) or {}).get("status") in (STATUS_ANSWERED, STATUS_NO_EXPERIENCE)


def record(
    backlog: dict[str, dict[str, Any]],
    topic: Topic,
    *,
    job_id: str,
    run_date: str,
) -> dict[str, Any]:
    entry = backlog.setdefault(
        topic.id,
        {"label": topic.label, "question": topic.question, "status": STATUS_OPEN,
         "count": 0, "first_seen": run_date, "jobs": []},
    )
    entry["label"], entry["question"] = topic.label, topic.question
    if job_id not in entry["jobs"]:
        entry["count"] = int(entry.get("count") or 0) + 1
        entry["jobs"] = (entry["jobs"] + [job_id])[-MAX_JOBS_PER_TOPIC:]
    entry["last_seen"] = run_date
    return entry


def set_status(topic_id: str, status: str, *, note: str | None = None,
               path: Path | None = None) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"Unknown status {status!r}; expected one of {sorted(VALID_STATUSES)}")
    backlog = load_backlog(path)
    if topic_id not in backlog:
        known = {t.id: t for t in load_lexicon()}
        if topic_id not in known:
            raise KeyError(f"Unknown topic {topic_id!r}")
        topic = known[topic_id]
        backlog[topic_id] = {"label": topic.label, "question": topic.question,
                             "count": 0, "jobs": []}
    backlog[topic_id]["status"] = status
    if note:
        backlog[topic_id]["note"] = note
    save_backlog(backlog, path)
    return backlog[topic_id]


def open_topics_ranked(backlog: dict[str, dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    rows = [(tid, e) for tid, e in backlog.items() if e.get("status", STATUS_OPEN) == STATUS_OPEN]
    return sorted(rows, key=lambda item: (-int(item[1].get("count") or 0), item[0]))
