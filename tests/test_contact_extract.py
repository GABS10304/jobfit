"""Tests for best-effort hiring-contact extraction (backend.sourcing.contact_extract)."""

from __future__ import annotations

from backend.sourcing.contact_extract import extract_hiring_contact


def test_extracts_name_with_scandinavian_diacritics():
    text = (
        "If you have any questions, you are welcome to contact the hiring "
        "manager, Rasmus Ræbild Jespersen – Cluster Lead, GenAI Adoption "
        "Squads on rjes@danskebank.dk"
    )
    result = extract_hiring_contact(text)
    assert result["name"] == "Rasmus Ræbild Jespersen"
    assert result["email"] == "rjes@danskebank.dk"


def test_extracts_german_ansprechpartner():
    text = "Bei Fragen wende dich an Julia Schmidt, julia.schmidt@company.com"
    result = extract_hiring_contact(text)
    assert result["name"] == "Julia Schmidt"
    assert result["email"] == "julia.schmidt@company.com"


def test_extracts_email_only_when_no_name_pattern():
    text = "Questions? Reach out to hr@company.com"
    result = extract_hiring_contact(text)
    assert result["email"] == "hr@company.com"


def test_returns_none_none_when_no_contact_info():
    result = extract_hiring_contact("This posting has no contact details at all.")
    assert result == {"name": None, "email": None}


def test_handles_empty_and_none_input():
    assert extract_hiring_contact("") == {"name": None, "email": None}
    assert extract_hiring_contact(None) == {"name": None, "email": None}


def test_does_not_capture_lowercase_trigger_words_as_name():
    """Regression: a naive case-insensitive name pattern would capture
    "the hiring manager" itself as the name."""
    text = "Please contact the hiring manager for more information."
    result = extract_hiring_contact(text)
    assert result["name"] != "The Hiring Manager"
    assert result["name"] != "the hiring manager"
