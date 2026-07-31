"""Calls the Claude API to draft a cover letter (Phase 1 SaaS blocker).

Replaces "Claude writes the Anschreiben live in the approval chat" with a
plain function call the backend can make on its own — the system prompt,
output schema, and input-building contract live in cover_letter_prompt.py;
this module is only the API call + response handling.

Not wired into prepare_application_draft.py yet — that pipeline stays
deterministic/API-free by design (see docs/SAAS_PRODUCT_IDEATION.md). This is
the building block a production endpoint (or a future automated version of
the approval flow) would call once ready.
"""

from __future__ import annotations

from typing import Any

import anthropic

from backend.generation.cover_letter_prompt import (
    COVER_LETTER_OUTPUT_SCHEMA,
    SYSTEM_PROMPT,
    build_user_message,
)

MODEL = "claude-opus-5"
_TOOL_NAME = COVER_LETTER_OUTPUT_SCHEMA["name"]


class CoverLetterRefusal(Exception):
    """Claude's safety classifiers declined the request (stop_reason == 'refusal').

    HTTP 200, not an API error — check stop_reason before assuming a tool
    call, per the claude-api skill's refusal-handling guidance.
    """

    def __init__(self, category: str | None, explanation: str | None):
        self.category = category
        self.explanation = explanation
        super().__init__(f"refused (category={category}): {explanation}")


class CoverLetterGenerationError(Exception):
    """The response didn't contain the forced tool call.

    Shouldn't happen with tool_choice forcing the tool, but surfaced
    explicitly rather than returning an empty/partial draft silently.
    """


def generate_cover_letter(
    context: dict[str, Any],
    *,
    client: anthropic.Anthropic | None = None,
) -> dict[str, Any]:
    """Draft a cover letter from prepare_application_draft.py's context.json shape.

    `context` must carry the fields build_user_message() reads: jd_text,
    company, title, matched_signals, missing_signals, person_name,
    person_location, cv_markdown (the fact source — see build_user_message's
    docstring for why this is already evidence-filtered).

    Returns the validated structured draft matching COVER_LETTER_OUTPUT_SCHEMA
    (sender_block, recipient_block, date_line, subject_line, salutation,
    paragraphs, closing_line, signature, flags).

    Retries for 429/5xx/connection errors are handled by the SDK's default
    max_retries (2) — this function does not add its own retry loop. Typed
    exceptions (anthropic.RateLimitError, anthropic.APIStatusError, etc.)
    propagate to the caller; catch them there, most-specific first.
    """
    client = client or anthropic.Anthropic()

    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[COVER_LETTER_OUTPUT_SCHEMA],
        tool_choice={"type": "tool", "name": _TOOL_NAME},
        messages=[{"role": "user", "content": build_user_message(context)}],
    )

    if response.stop_reason == "refusal":
        details = response.stop_details
        raise CoverLetterRefusal(
            category=details.category if details else None,
            explanation=details.explanation if details else None,
        )

    for block in response.content:
        if block.type == "tool_use" and block.name == _TOOL_NAME:
            return block.input

    raise CoverLetterGenerationError(
        f"Expected a '{_TOOL_NAME}' tool call, got stop_reason={response.stop_reason!r}"
    )
