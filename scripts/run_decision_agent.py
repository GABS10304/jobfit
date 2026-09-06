"""Run the advocate/skeptic/decision agent council on one tracked job.

Decides whether pursuing a job is worth Gabriel's time — draft an
application, attempt direct outreach (if a hiring contact was found),
both, or skip — before any drafting effort is spent. Never sends anything;
that stays a human action (see decision_agent_service.py's scope note).

Deliberately Gabriel-only, unlike add_manual_job.py / prepare_application_draft.py:
decision_agent_prompt.py's system prompts are hard-coded to "Gabriel Strecker"
and his stated motivation order (Autonomie > Wirkung > Geld), not generic
advice. This script has no --user-id and always scores/reasons against
domain/*.yaml regardless of whose job_id you pass it — if you run it on a job
that a different onboarded user (profiles/<user_id>/) added, it silently
evaluates Gabriel's fit for that job, not theirs, with no warning. Making this
generic would mean rewriting the prompts themselves, not just the data
loading — a bigger, separate task. See SECURITY.md.

Usage:
  python scripts/run_decision_agent.py --job-id 24163_product-owner-genai-use-case-acceleration
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.generation.decision_agent_service import (  # noqa: E402
    DecisionAgentError,
    DecisionAgentRefusal,
    evaluate_job_for_pursuit,
)
from scripts.prepare_application_draft import build_context  # noqa: E402

DEFAULT_REVIEW_DIR = REPO_ROOT / "out" / "review"


def run(job_id: str, *, review_dir: Path = DEFAULT_REVIEW_DIR) -> dict:
    context = build_context(job_id)
    result = evaluate_job_for_pursuit(context)

    out_dir = review_dir / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "decision.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--review-dir", type=Path, default=DEFAULT_REVIEW_DIR)
    args = parser.parse_args()

    try:
        result = run(args.job_id, review_dir=args.review_dir)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (DecisionAgentRefusal, DecisionAgentError) as exc:
        print(f"Agent failed ({type(exc).__name__}): {exc}", file=sys.stderr)
        print("Fail open: treat as flag_for_review, decide manually.", file=sys.stderr)
        return 1

    decision = result["decision"]
    advocate = result["advocate"]
    skeptic = result["skeptic"]

    print(f"=== {args.job_id} ===")
    print(f"🟢 Advocate ({advocate.get('excitement_level', '?')}): {advocate.get('case_for_pursuing', '?')}")
    print(f"🔴 Skeptic ({skeptic.get('concern_level', '?')}): {skeptic.get('case_against_pursuing', '?')}")
    print(
        f"\n⚖️  Decision: {decision['decision'].upper()} "
        f"(confidence={decision['confidence']}, action={decision['recommended_action']})"
    )
    print(f"    {decision['reasoning']}")
    print(f"\nwritten: {args.review_dir / args.job_id / 'decision.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
