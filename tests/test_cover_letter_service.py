"""Tests for the cover-letter generation service — mocked Anthropic client,
no real API calls (no credentials configured, and no reason to spend real
money on a unit test in any case).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.generation.cover_letter_service import (
    CoverLetterGenerationError,
    CoverLetterRefusal,
    generate_cover_letter,
)

SAMPLE_CONTEXT = {
    "job_id": "999_test-role",
    "title": "Senior Product Manager (m/w/d)",
    "company": "testco",
    "url": "https://example.jobs.personio.de/job/999",
    "jd_text": "Senior Product Manager gesucht, GovTech, Remote.",
    "role_id": "ai_product_manager",
    "role_name": "Product Manager / AI Product Manager",
    "role_score": 90,
    "matched_signals": ["product_discovery", "b2b_saas"],
    "missing_signals": ["govtech"],
    "person_name": "Gabriel Strecker",
    "person_location": "Marktheidenfeld, Bayern, Deutschland",
    "impact_notes": None,
    "cv_markdown": "# Gabriel Strecker\n\n## Berufserfahrung\n- Beispiel-Bullet.\n",
}

VALID_DRAFT = {
    "sender_block": "Gabriel Strecker\nMarktheidenfeld",
    "recipient_block": "testco\nRecruiting",
    "date_line": "Marktheidenfeld, 31. Juli 2026",
    "subject_line": "Bewerbung als Senior Product Manager (m/w/d)",
    "salutation": "Sehr geehrte Damen und Herren,",
    "paragraphs": ["Absatz eins.", "Absatz zwei.", "Absatz drei."],
    "closing_line": "Mit freundlichen Grüßen",
    "signature": "Gabriel Strecker",
    "flags": [],
}


def _mock_response(*, stop_reason: str, content: list, stop_details=None):
    return SimpleNamespace(stop_reason=stop_reason, content=content, stop_details=stop_details)


def test_generate_cover_letter_returns_tool_input_on_success():
    tool_block = SimpleNamespace(type="tool_use", name="submit_cover_letter", input=VALID_DRAFT)
    response = _mock_response(stop_reason="tool_use", content=[tool_block])
    client = MagicMock()
    client.messages.create.return_value = response

    result = generate_cover_letter(SAMPLE_CONTEXT, client=client)

    assert result == VALID_DRAFT
    call_kwargs = client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-5"
    assert call_kwargs["tool_choice"] == {"type": "tool", "name": "submit_cover_letter"}
    assert call_kwargs["tools"][0]["name"] == "submit_cover_letter"
    assert "Senior Product Manager gesucht" in call_kwargs["messages"][0]["content"]


def test_generate_cover_letter_raises_on_refusal():
    details = SimpleNamespace(category="cyber", explanation="policy decline")
    response = _mock_response(stop_reason="refusal", content=[], stop_details=details)
    client = MagicMock()
    client.messages.create.return_value = response

    with pytest.raises(CoverLetterRefusal) as exc_info:
        generate_cover_letter(SAMPLE_CONTEXT, client=client)

    assert exc_info.value.category == "cyber"
    assert exc_info.value.explanation == "policy decline"


def test_generate_cover_letter_raises_on_refusal_without_stop_details():
    response = _mock_response(stop_reason="refusal", content=[], stop_details=None)
    client = MagicMock()
    client.messages.create.return_value = response

    with pytest.raises(CoverLetterRefusal) as exc_info:
        generate_cover_letter(SAMPLE_CONTEXT, client=client)

    assert exc_info.value.category is None
    assert exc_info.value.explanation is None


def test_generate_cover_letter_raises_when_tool_call_missing():
    text_block = SimpleNamespace(type="text", text="oops, no tool call")
    response = _mock_response(stop_reason="end_turn", content=[text_block])
    client = MagicMock()
    client.messages.create.return_value = response

    with pytest.raises(CoverLetterGenerationError):
        generate_cover_letter(SAMPLE_CONTEXT, client=client)


def test_generate_cover_letter_ignores_unrelated_tool_blocks():
    other_tool = SimpleNamespace(type="tool_use", name="some_other_tool", input={"x": 1})
    target_tool = SimpleNamespace(type="tool_use", name="submit_cover_letter", input=VALID_DRAFT)
    response = _mock_response(stop_reason="tool_use", content=[other_tool, target_tool])
    client = MagicMock()
    client.messages.create.return_value = response

    result = generate_cover_letter(SAMPLE_CONTEXT, client=client)

    assert result == VALID_DRAFT
