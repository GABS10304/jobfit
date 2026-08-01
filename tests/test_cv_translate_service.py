"""Tests for the CV translation service — mocked Anthropic client, no real
API calls (no credentials configured, and no reason to spend real money on
a unit test in any case).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.generation.cv_translate_service import (
    CvTranslationError,
    CvTranslationRefusal,
    translate_cv_markdown,
)

SAMPLE_MARKDOWN = (
    "# Gabriel Strecker\n\n"
    "## Berufserfahrung\n\n"
    "### Product Manager – RIWA GmbH\n"
    "2025-06 – heute | Remote\n\n"
    "- Agentic-AI-Produktideen validieren.\n"
    "- MCP-Prototypen bauen.\n"
)

TRANSLATED_MARKDOWN = (
    "# Gabriel Strecker\n\n"
    "## Professional Experience\n\n"
    "### Product Manager – RIWA GmbH\n"
    "2025-06 – present | Remote\n\n"
    "- Validate agentic AI product ideas.\n"
    "- Build MCP prototypes.\n"
)

# Same content, but one bullet merged into one line — must be rejected.
TRUNCATED_TRANSLATION = (
    "# Gabriel Strecker\n\n"
    "## Professional Experience\n\n"
    "### Product Manager – RIWA GmbH\n"
    "2025-06 – present | Remote\n\n"
    "- Validate agentic AI product ideas and build MCP prototypes.\n"
)


def _mock_response(*, stop_reason: str, content: list, stop_details=None):
    return SimpleNamespace(stop_reason=stop_reason, content=content, stop_details=stop_details)


def test_translate_cv_markdown_returns_translation_on_success():
    tool_block = SimpleNamespace(
        type="tool_use",
        name="submit_cv_translation",
        input={"translated_markdown": TRANSLATED_MARKDOWN},
    )
    response = _mock_response(stop_reason="tool_use", content=[tool_block])
    client = MagicMock()
    client.messages.create.return_value = response

    result = translate_cv_markdown(SAMPLE_MARKDOWN, client=client)

    assert result == TRANSLATED_MARKDOWN
    call_kwargs = client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-5"
    assert call_kwargs["tool_choice"] == {"type": "tool", "name": "submit_cv_translation"}
    assert "Agentic-AI-Produktideen" in call_kwargs["messages"][0]["content"]


def test_translate_cv_markdown_raises_on_refusal():
    details = SimpleNamespace(category="cyber", explanation="policy decline")
    response = _mock_response(stop_reason="refusal", content=[], stop_details=details)
    client = MagicMock()
    client.messages.create.return_value = response

    with pytest.raises(CvTranslationRefusal) as exc_info:
        translate_cv_markdown(SAMPLE_MARKDOWN, client=client)

    assert exc_info.value.category == "cyber"


def test_translate_cv_markdown_raises_when_tool_call_missing():
    text_block = SimpleNamespace(type="text", text="oops")
    response = _mock_response(stop_reason="end_turn", content=[text_block])
    client = MagicMock()
    client.messages.create.return_value = response

    with pytest.raises(CvTranslationError):
        translate_cv_markdown(SAMPLE_MARKDOWN, client=client)


def test_translate_cv_markdown_rejects_bullet_count_mismatch():
    """Guards against the model silently merging/dropping facts."""
    tool_block = SimpleNamespace(
        type="tool_use",
        name="submit_cv_translation",
        input={"translated_markdown": TRUNCATED_TRANSLATION},
    )
    response = _mock_response(stop_reason="tool_use", content=[tool_block])
    client = MagicMock()
    client.messages.create.return_value = response

    with pytest.raises(CvTranslationError, match="Bullet-line count changed"):
        translate_cv_markdown(SAMPLE_MARKDOWN, client=client)


def test_translate_cv_markdown_ignores_unrelated_tool_blocks():
    other_tool = SimpleNamespace(type="tool_use", name="some_other_tool", input={"x": 1})
    target_tool = SimpleNamespace(
        type="tool_use",
        name="submit_cv_translation",
        input={"translated_markdown": TRANSLATED_MARKDOWN},
    )
    response = _mock_response(stop_reason="tool_use", content=[other_tool, target_tool])
    client = MagicMock()
    client.messages.create.return_value = response

    result = translate_cv_markdown(SAMPLE_MARKDOWN, client=client)

    assert result == TRANSLATED_MARKDOWN
