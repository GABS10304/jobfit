"""Calls the Claude API to translate a deterministically-generated CV (DE -> EN).

Used when the job posting itself is in English (see
backend/sourcing/language_detect.py). SelectionPlan / bullet selection stays
100% deterministic; this only translates the final rendered text — see
cv_translate_prompt.py for why that's a narrow, deliberate exception to the
"CV generation is 100% deterministic, no LLM" rule, not a loosening of it.

Same call shape as cover_letter_service.py: forced tool-use, refusal
handling per the claude-api skill, no custom retry loop (SDK default
max_retries=2 covers 429/5xx).
"""

from __future__ import annotations

import re

import anthropic

from backend.generation.cv_translate_prompt import (
    CV_TRANSLATION_OUTPUT_SCHEMA,
    SYSTEM_PROMPT,
    build_user_message,
)

MODEL = "claude-opus-5"
_TOOL_NAME = CV_TRANSLATION_OUTPUT_SCHEMA["name"]
_BULLET_LINE_RE = re.compile(r"^- ", re.MULTILINE)


class CvTranslationRefusal(Exception):
    """Claude's safety classifiers declined the request (stop_reason == 'refusal').

    HTTP 200, not an API error — check stop_reason before assuming a tool
    call, per the claude-api skill's refusal-handling guidance.
    """

    def __init__(self, category: str | None, explanation: str | None):
        self.category = category
        self.explanation = explanation
        super().__init__(f"refused (category={category}): {explanation}")


class CvTranslationError(Exception):
    """The response didn't contain the forced tool call, or failed validation."""


def translate_cv_markdown(
    cv_markdown: str,
    *,
    client: anthropic.Anthropic | None = None,
) -> str:
    """Translate a German CV markdown string into English.

    Validates that the translation preserves the same bullet-line count as
    the input as a cheap, deterministic guard against the model silently
    dropping or merging facts — raises CvTranslationError if they diverge,
    rather than returning a possibly-incomplete translation silently.
    """
    client = client or anthropic.Anthropic()

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[CV_TRANSLATION_OUTPUT_SCHEMA],
        tool_choice={"type": "tool", "name": _TOOL_NAME},
        messages=[{"role": "user", "content": build_user_message(cv_markdown)}],
    )

    if response.stop_reason == "refusal":
        details = response.stop_details
        raise CvTranslationRefusal(
            category=details.category if details else None,
            explanation=details.explanation if details else None,
        )

    translated: str | None = None
    for block in response.content:
        if block.type == "tool_use" and block.name == _TOOL_NAME:
            translated = block.input.get("translated_markdown")
            break

    if translated is None:
        raise CvTranslationError(
            f"Expected a '{_TOOL_NAME}' tool call, got stop_reason={response.stop_reason!r}"
        )

    input_bullets = len(_BULLET_LINE_RE.findall(cv_markdown))
    output_bullets = len(_BULLET_LINE_RE.findall(translated))
    if input_bullets != output_bullets:
        raise CvTranslationError(
            f"Bullet-line count changed during translation ({input_bullets} -> "
            f"{output_bullets}) — refusing a possibly-incomplete/altered CV."
        )

    return translated
