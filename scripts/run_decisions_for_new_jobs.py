"""Run the advocate/skeptic/decision agent on every job_id in a JSON list.

Meant to be called by daily_sourcing_run.sh after the day's shortlist(s)
are built — the list of new job_ids comes from build_daily_shortlist.py's
--new-ids-out. Fails open per job: a missing API key / refusal / transient
error skips that one job (flag_for_review by omission — nothing gets
silently marked "decided" without a real decision) rather than aborting the
whole daily run.

Usage:
  python scripts/run_decisions_for_new_jobs.py --job-ids-file out/daily/new_jobs_20260801.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_decision_agent import run as run_decision_agent  # noqa: E402


def run_decisions(job_ids: list[str], *, decide=run_decision_agent) -> dict:
    """Run the decision agent on each job_id; fail open per job (see module
    docstring). `decide` is injectable for tests."""
    print(f"=== decision agent: {len(job_ids)} new job(s) ===")
    pursue_count = 0
    skipped_agent_errors = 0
    results: dict[str, dict] = {}

    for job_id in job_ids:
        try:
            result = decide(job_id)
        except Exception as exc:  # noqa: BLE001 - fail open per job, see docstring
            print(f"  {job_id}: agent failed ({type(exc).__name__}: {exc}) — skipped, decide manually")
            skipped_agent_errors += 1
            continue

        results[job_id] = result
        decision = result["decision"]
        print(
            f"  {job_id}: {decision['decision'].upper()} "
            f"(confidence={decision['confidence']}, action={decision['recommended_action']})"
        )
        if decision["decision"] == "pursue":
            pursue_count += 1

    print(f"\n{pursue_count}/{len(job_ids)} recommended to pursue.")
    if skipped_agent_errors:
        print(f"{skipped_agent_errors} skipped due to agent errors (see above) — check manually.")

    return {
        "results": results,
        "pursue_count": pursue_count,
        "skipped_agent_errors": skipped_agent_errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-ids-file", type=Path, required=True)
    args = parser.parse_args()

    if not args.job_ids_file.exists():
        print(f"no new-job-ids file at {args.job_ids_file}, nothing to decide on")
        return 0

    job_ids = json.loads(args.job_ids_file.read_text(encoding="utf-8"))
    if not job_ids:
        print("no new jobs today, nothing to decide on")
        return 0

    run_decisions(job_ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
