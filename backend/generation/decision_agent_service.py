"""The job-pursuit decision agent: advocate + skeptic + decision-maker.

Three sequential Claude API calls (see decision_agent_prompt.py for why not
one call pretending to be two voices), same forced-tool-use + refusal-
handling contract as cover_letter_service.py / cv_translate_service.py.

Scope boundary (deliberate, not a gap): this agent decides whether to
PURSUE a job (draft an application / attempt direct outreach) or SKIP/FLAG
it. It never sends anything. Whether job-fit-system ever auto-sends is a
decision Gabriel makes explicitly (see domain/constraints.yaml
application_rules.auto_apply_enabled, still false) — not something this
agent escalates into on its own.
"""

from __future__ import annotations

from typing import Any

import anthropic

from backend.generation.decision_agent_prompt import (
    ADVOCATE_OUTPUT_SCHEMA,
    ADVOCATE_SYSTEM_PROMPT,
    DECISION_OUTPUT_SCHEMA,
    DECISION_SYSTEM_PROMPT,
    SKEPTIC_OUTPUT_SCHEMA,
    SKEPTIC_SYSTEM_PROMPT,
    build_advocate_message,
    build_decision_message,
    build_skeptic_message,
)

MODEL = "claude-opus-5"


class DecisionAgentRefusal(Exception):
    """Claude's safety classifiers declined one of the three calls."""

    def __init__(self, stage: str, category: str | None, explanation: str | None):
        self.stage = stage
        self.category = category
        self.explanation = explanation
        super().__init__(f"{stage} refused (category={category}): {explanation}")


class DecisionAgentError(Exception):
    """A call didn't return the forced tool call."""


def _call_tool(
    client: anthropic.Anthropic,
    *,
    stage: str,
    system: str,
    schema: dict,
    user_message: str,
) -> dict[str, Any]:
    tool_name = schema["name"]
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=system,
        tools=[schema],
        tool_choice={"type": "tool", "name": tool_name},
        messages=[{"role": "user", "content": user_message}],
    )

    if response.stop_reason == "refusal":
        details = response.stop_details
        raise DecisionAgentRefusal(
            stage=stage,
            category=details.category if details else None,
            explanation=details.explanation if details else None,
        )

    for block in response.content:
        if block.type == "tool_use" and block.name == tool_name:
            return block.input

    raise DecisionAgentError(
        f"{stage}: expected a '{tool_name}' tool call, got stop_reason={response.stop_reason!r}"
    )


def evaluate_job_for_pursuit(
    context: dict[str, Any],
    *,
    client: anthropic.Anthropic | None = None,
) -> dict[str, Any]:
    """Run the advocate -> skeptic -> decision pipeline for one job.

    `context` needs the fields decision_agent_prompt.build_facts_block()
    reads: jd_text, company, title, role_score, role_name, matched_signals,
    missing_signals, location_match, hiring_contact, cv_markdown.

    Returns {"advocate": {...}, "skeptic": {...}, "decision": {...}}.
    Raises DecisionAgentRefusal / DecisionAgentError from whichever stage
    failed — callers should catch and fail open (flag for manual review)
    rather than silently dropping the job, same pattern as
    prepare_application_draft.py's CV-translation fallback.
    """
    client = client or anthropic.Anthropic()

    advocate = _call_tool(
        client,
        stage="advocate",
        system=ADVOCATE_SYSTEM_PROMPT,
        schema=ADVOCATE_OUTPUT_SCHEMA,
        user_message=build_advocate_message(context),
    )
    skeptic = _call_tool(
        client,
        stage="skeptic",
        system=SKEPTIC_SYSTEM_PROMPT,
        schema=SKEPTIC_OUTPUT_SCHEMA,
        user_message=build_skeptic_message(context),
    )
    decision = _call_tool(
        client,
        stage="decision",
        system=DECISION_SYSTEM_PROMPT,
        schema=DECISION_OUTPUT_SCHEMA,
        user_message=build_decision_message(context, advocate, skeptic),
    )

    return {"advocate": advocate, "skeptic": skeptic, "decision": decision}
