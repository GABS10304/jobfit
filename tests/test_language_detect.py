"""Tests for the JD language heuristic (backend.sourcing.language_detect)."""

from __future__ import annotations

from backend.sourcing.language_detect import detect_jd_language

GERMAN_JD = (
    "Wir suchen eine erfahrene Person für unser Team in Berlin. "
    "Du arbeitest eng mit unserem Produkt- und Engineering-Team zusammen und "
    "bringst mehrjährige Erfahrung im Bereich Produktmanagement mit. "
    "Kenntnisse über agile Arbeitsweisen sind von Vorteil."
)

ENGLISH_JD = (
    "We are looking for an experienced Senior Product Manager to join our team. "
    "You will work closely with engineering and design, and bring years of "
    "experience building B2B SaaS products. Strong communication skills required."
)


def test_detects_german_jd():
    assert detect_jd_language(GERMAN_JD) == "de"


def test_detects_english_jd():
    assert detect_jd_language(ENGLISH_JD) == "en"


def test_defaults_to_german_on_empty_text():
    assert detect_jd_language("") == "de"
    assert detect_jd_language(None) == "de"


def test_defaults_to_german_on_no_signal():
    assert detect_jd_language("123 456 789") == "de"


def test_umlauts_alone_tip_towards_german():
    assert detect_jd_language("Wir suchen jemanden für Qualitätssicherung.") == "de"
