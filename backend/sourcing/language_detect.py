"""Lightweight German-vs-English detection for job description text.

No external dependency (no langdetect/fasttext) — a stopword-frequency
heuristic is plenty reliable for JD-length text and keeps this deterministic
and dependency-free, consistent with the rest of backend/sourcing/*.
"""

from __future__ import annotations

import re
from typing import Literal

_TOKEN_RE = re.compile(r"[a-zäöüß]+", re.IGNORECASE)

# Function words that are unambiguous in one language and rare/absent in the
# other — deliberately excludes cognates/ambiguous short words (e.g. "in",
# "an", "was" reads as English "was"/German "was").
_DE_MARKERS = frozenset(
    {
        "und", "der", "die", "das", "mit", "für", "eine", "einen", "einer",
        "ist", "sind", "wir", "sie", "sich", "auch", "nicht", "werden",
        "unser", "unsere", "unserem", "unseren", "haben", "hast", "kannst",
        "über", "mehr", "sowie", "bei", "auf", "von", "zum", "zur", "als",
        "diese", "dieser", "dieses", "gute", "guten", "arbeiten", "team",
        "erfahrung", "kenntnisse", "aufgaben", "unternehmen", "job",
    }
)
_EN_MARKERS = frozenset(
    {
        "the", "and", "with", "for", "you", "your", "we", "are", "is",
        "our", "this", "that", "will", "have", "has", "role", "team",
        "experience", "skills", "responsibilities", "job", "work",
        "about", "who", "what", "join", "looking", "years",
    }
)


def detect_jd_language(text: str | None) -> Literal["de", "en"]:
    """Best-effort DE/EN guess. Defaults to "de" (the majority of this
    system's sourcing boards are German) when the signal is weak or absent."""
    if not text or not text.strip():
        return "de"

    tokens = [t.casefold() for t in _TOKEN_RE.findall(text)]
    if not tokens:
        return "de"

    de_hits = sum(1 for t in tokens if t in _DE_MARKERS)
    en_hits = sum(1 for t in tokens if t in _EN_MARKERS)

    # German-specific characters are a strong, cheap signal on their own.
    umlaut_hits = len(re.findall(r"[äöüßÄÖÜ]", text))
    de_hits += umlaut_hits

    if de_hits == 0 and en_hits == 0:
        return "de"
    return "en" if en_hits > de_hits else "de"
