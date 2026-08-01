"""Tests for advisory location matching (backend.sourcing.filtering)."""

from __future__ import annotations

from backend.models import LocationPreferences
from backend.sourcing.filtering import (
    RELOCATION_NOTE_MIN_SCORE,
    evaluate_location_fit,
    relocation_note,
)

PREFS = LocationPreferences(
    preferred_locations=["Remote", "Germany", "DACH"], avoid_locations=[]
)


def test_evaluate_location_fit_matches_preferred():
    result = evaluate_location_fit("Senior PM, Berlin, Germany, Remote-first", PREFS)
    assert result["match"] == "preferred"
    assert result["note"] is None


def test_evaluate_location_fit_flags_outside_preferred():
    result = evaluate_location_fit("Senior PM, Copenhagen, Denmark, Hybrid", PREFS)
    assert result["match"] == "outside_preferred"
    assert result["note"]


def test_evaluate_location_fit_flags_avoid_location():
    prefs = LocationPreferences(preferred_locations=["Germany"], avoid_locations=["Denmark"])
    result = evaluate_location_fit("Senior PM, Copenhagen, Denmark", prefs)
    assert result["match"] == "avoid"


def test_evaluate_location_fit_returns_unknown_without_preferences():
    result = evaluate_location_fit("Senior PM, Copenhagen", None)
    assert result["match"] == "unknown"
    assert result["note"] is None


def test_evaluate_location_fit_dach_synonym_matches_austria():
    prefs = LocationPreferences(preferred_locations=["DACH"], avoid_locations=[])
    result = evaluate_location_fit("Senior PM, Vienna, Austria", prefs)
    assert result["match"] == "preferred"


def test_relocation_note_fires_for_solid_score_outside_preferred():
    note = relocation_note(RELOCATION_NOTE_MIN_SCORE, "outside_preferred")
    assert note is not None
    assert "Umzugsbereitschaft" in note


def test_relocation_note_silent_below_threshold():
    assert relocation_note(RELOCATION_NOTE_MIN_SCORE - 1, "outside_preferred") is None


def test_relocation_note_silent_when_preferred():
    assert relocation_note(90, "preferred") is None


def test_relocation_note_silent_without_score():
    assert relocation_note(None, "outside_preferred") is None
