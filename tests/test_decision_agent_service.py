"""Tests for the advocate/skeptic/decision agent — mocked Anthropic client,
no real API calls (no credentials configured, and no reason to spend real
money on a unit test in any case).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.generation.decision_agent_service import (
    DecisionAgentError,
    DecisionAgentRefusal,
    evaluate_job_for_pursuit,
)

SAMPLE_CONTEXT = {
    "job_id": "999_test-role",
    "title": "Senior Product Manager",
    "company": "TestCo",
    "jd_text": "Senior PM, full ownership, flat hierarchy, founding role.",
    "role_score": 82,
    "role_name": "Product Manager / AI Product Manager",
    "matched_signals": ["product_discovery"],
    "missing_signals": ["mvp_validation"],
    "location_match": "preferred",
    "hiring_contact": {"name": "Jane Doe", "email": "jane@testco.com"},
    "cv_markdown": "# Gabriel Strecker\n\n## Berufserfahrung\n- Beispiel-Bullet.\n",
}

ADVOCATE_RESULT = {
    "case_for_pursuing": "Starke Übereinstimmung mit Autonomie-Wunsch.",
    "key_strengths": ["Full ownership", "Founding role"],
    "excitement_level": "high",
}

SKEPTIC_RESULT = {
    "case_against_pursuing": "MVP-Validierung fehlt als Signal.",
    "key_risks": ["Score nicht bei Strong-Pass"],
    "red_flags": [],
    "concern_level": "moderate",
}

DECISION_RESULT = {
    "decision": "pursue",
    "recommended_action": "draft_application",
    "reasoning": "Autonomie-Signale überwiegen die fehlenden Skill-Signale.",
    "confidence": "medium",
}


def _tool_block(name: str, input_: dict):
    return SimpleNamespace(type="tool_use", name=name, input=input_)


def _response(*, stop_reason: str, content: list, stop_details=None):
    return SimpleNamespace(stop_reason=stop_reason, content=content, stop_details=stop_details)


def test_evaluate_job_for_pursuit_runs_all_three_stages_in_order():
    client = MagicMock()
    client.messages.create.side_effect = [
        _response(
            stop_reason="tool_use",
            content=[_tool_block("submit_advocate_case", ADVOCATE_RESULT)],
        ),
        _response(
            stop_reason="tool_use",
            content=[_tool_block("submit_skeptic_case", SKEPTIC_RESULT)],
        ),
        _response(
            stop_reason="tool_use",
            content=[_tool_block("submit_decision", DECISION_RESULT)],
        ),
    ]

    result = evaluate_job_for_pursuit(SAMPLE_CONTEXT, client=client)

    assert result["advocate"] == ADVOCATE_RESULT
    assert result["skeptic"] == SKEPTIC_RESULT
    assert result["decision"] == DECISION_RESULT
    assert client.messages.create.call_count == 3

    calls = client.messages.create.call_args_list
    assert calls[0].kwargs["tool_choice"] == {"type": "tool", "name": "submit_advocate_case"}
    assert calls[1].kwargs["tool_choice"] == {"type": "tool", "name": "submit_skeptic_case"}
    assert calls[2].kwargs["tool_choice"] == {"type": "tool", "name": "submit_decision"}
    for call in calls:
        assert call.kwargs["model"] == "claude-opus-5"

    # Decision stage must see both prior verdicts, not just the raw facts.
    decision_message = calls[2].kwargs["messages"][0]["content"]
    assert "Starke Übereinstimmung" in decision_message
    assert "MVP-Validierung fehlt" in decision_message


def test_evaluate_job_for_pursuit_raises_on_advocate_refusal():
    details = SimpleNamespace(category="cyber", explanation="policy decline")
    client = MagicMock()
    client.messages.create.return_value = _response(
        stop_reason="refusal", content=[], stop_details=details
    )

    with pytest.raises(DecisionAgentRefusal) as exc_info:
        evaluate_job_for_pursuit(SAMPLE_CONTEXT, client=client)

    assert exc_info.value.stage == "advocate"
    assert client.messages.create.call_count == 1  # stops at first failure


def test_evaluate_job_for_pursuit_raises_on_skeptic_refusal():
    client = MagicMock()
    client.messages.create.side_effect = [
        _response(
            stop_reason="tool_use",
            content=[_tool_block("submit_advocate_case", ADVOCATE_RESULT)],
        ),
        _response(stop_reason="refusal", content=[], stop_details=None),
    ]

    with pytest.raises(DecisionAgentRefusal) as exc_info:
        evaluate_job_for_pursuit(SAMPLE_CONTEXT, client=client)

    assert exc_info.value.stage == "skeptic"
    assert client.messages.create.call_count == 2


def test_evaluate_job_for_pursuit_raises_when_tool_call_missing():
    client = MagicMock()
    client.messages.create.return_value = _response(
        stop_reason="end_turn", content=[SimpleNamespace(type="text", text="oops")]
    )

    with pytest.raises(DecisionAgentError):
        evaluate_job_for_pursuit(SAMPLE_CONTEXT, client=client)
