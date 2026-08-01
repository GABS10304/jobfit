"""Best-effort extraction of a named hiring contact from JD text.

Many postings name the hiring manager directly (see the Danske Bank JD this
was built from: "you are welcome to contact the hiring manager, Rasmus
Ræbild Jespersen ... on rjes@danskebank.dk"). When present, this is the
concrete hook for direct outreach instead of only competing in the ATS
funnel — deliberately just extraction (regex, deterministic), not judgment
about whether/how to reach out; that stays a human (chat) decision.
"""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}")

# Name-word pattern uses the Latin-1 Supplement ranges (À-Ö, Ø-Þ / à-ö, ø-ÿ)
# rather than just German äöüß — covers Scandinavian names (æ, ø, å) and most
# other Western European accented letters too (real example this was built
# against: "Rasmus Ræbild Jespersen").
_NAME_WORD = r"[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ'-]+"

# Trigger phrases that usually precede a named contact (DE/EN). Only the
# trigger is case-insensitive — the name-capture group stays case-sensitive
# (a global IGNORECASE would let lowercase words like "the" satisfy the
# capitalized-name pattern, capturing junk like "the hiring manager").
_CONTACT_TRIGGER_RE = re.compile(
    r"(?i:hiring manager|contact person|contact|ansprechpartner(?:in)?|"
    r"wende dich an|kontaktiere|fragen an|questions[,:]?\s*(?:please\s+)?contact)"
    r"[^.\n]{0,80}?"
    rf"({_NAME_WORD}(?:[\s-]{_NAME_WORD}){{1,3}})"
)


def extract_hiring_contact(jd_text: str | None) -> dict:
    """Return {"name": str|None, "email": str|None} — either may be missing."""
    if not jd_text:
        return {"name": None, "email": None}

    emails = _EMAIL_RE.findall(jd_text)
    email = emails[0] if emails else None

    name = None
    match = _CONTACT_TRIGGER_RE.search(jd_text)
    if match:
        name = match.group(1).strip()

    return {"name": name, "email": email}
