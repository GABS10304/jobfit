"""Best-effort salary extraction from free-text JDs.

Deterministic regex only, no invention: if the JD does not state a figure we
cannot parse, ``extract_salary_range`` returns ``None`` and the gate simply
does not filter (missing data must never be treated as a rejection).

Covers common German formats: "70.000 - 90.000 €", "70.000€ - 90.000€",
"70.000 bis 90.000 Euro", "75k - 90k EUR", single figures with a currency or
salary-context word nearby ("75.000 € Jahresgehalt"). Does not attempt to
parse every possible phrasing (e.g. tariff tables, "TVöD E13").
"""

from __future__ import annotations

import re

_NUM = r"\d{1,3}(?:\.\d{3})+|\d{2,3}k"
_CURRENCY = r"(?:€|eur\w*)"
_CONTEXT_WORDS = r"(?:gehalt|jahresgehalt|brutto|jährlich|salary)"

_RANGE_RE = re.compile(
    rf"(?P<a>{_NUM})\s*{_CURRENCY}?\s*(?:-|–|bis|und)\s*(?P<b>{_NUM})\s*{_CURRENCY}?",
    re.IGNORECASE,
)
_SINGLE_WITH_CURRENCY_RE = re.compile(
    rf"(?P<a>{_NUM})\s*{_CURRENCY}",
    re.IGNORECASE,
)
_SINGLE_WITH_CONTEXT_RE = re.compile(
    rf"(?P<a>{_NUM})\s*(?:€|eur\w*)?\s*{_CONTEXT_WORDS}"
    rf"|{_CONTEXT_WORDS}[^.\n]{{0,20}}?(?P<b>{_NUM})",
    re.IGNORECASE,
)


def _to_number(raw: str) -> float:
    raw = raw.strip()
    if raw.casefold().endswith("k"):
        return float(raw[:-1].replace(".", "").replace(",", ".")) * 1000
    return float(raw.replace(".", "").replace(",", ""))


def extract_salary_range(text: str | None) -> tuple[float, float] | None:
    """Return (low, high) annual base in the JD's stated currency, or None."""
    if not text or not text.strip():
        return None

    range_match = _RANGE_RE.search(text)
    if range_match:
        a = _to_number(range_match.group("a"))
        b = _to_number(range_match.group("b"))
        return (a, b) if a <= b else (b, a)

    single_match = _SINGLE_WITH_CURRENCY_RE.search(
        text
    ) or _SINGLE_WITH_CONTEXT_RE.search(text)
    if single_match:
        raw = single_match.group("a") or single_match.group("b")
        value = _to_number(raw)
        return value, value

    return None


def passes_salary_gate(jd_text: str | None, min_annual_base: float | None) -> bool:
    """True unless the JD states a figure whose upper bound is clearly below the floor.

    No floor set, or no parseable figure in the JD → always passes (fail-open,
    consistent with "nichts erfinden" for missing data).
    """
    if min_annual_base is None:
        return True
    parsed = extract_salary_range(jd_text)
    if parsed is None:
        return True
    _low, high = parsed
    return high >= min_annual_base
