#!/usr/bin/env python3
"""Guards for this repo's riskiest fork-and-run surfaces.

Run from anywhere: python tools/security_guards.py

This repo ships pre-approved Claude Code permissions (`.claude/settings.json`)
that every fork user's Claude Code session executes without a prompt. These
guards make the dangerous changes LOUD, not impossible: a PR that intentionally
needs one of them must update the allowlists in this file in the same diff, so
the change is explicit and reviewable rather than buried.

Checks:
1. .claude/settings.json — every permissions.allow entry must be in the exact
   allowlist below. Catches permission widening (e.g. Bash(*), Bash(curl:*)),
   which would auto-approve commands on every fork. The same file's `hooks`
   key is held to an allowlist too: a hook runs automatically when its event
   fires, with no prompt, so it is strictly more dangerous than a pre-approved
   permission — this is the exact vector the Shai-Hulud worm used in its
   August 2026 wave, planting a SessionStart hook that ran on session start
   (https://research.jfrog.com/post/shai-hulud-is-back-august/). This repo
   ships no hooks at all; ALLOWED_HOOKS is empty on purpose.
2. .gitignore — the personal-data ignore rules must all still be present, and
   no un-allowlisted negation (!pattern) may re-include them. Catches
   weakening that would make future users silently commit their profile,
   generated applications, or personal assets.

Honest limit: a PR can edit this workflow/this file itself, so these guards
catch accidents and casual attempts, not a determined author — branch
protection with required checks and human review of workflow/settings diffs
remain the real backstop.

Stdlib only. Exit 0 on success, 1 with a failure list otherwise.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
errors: list[str] = []

# The exact permission entries this repo ships. A PR that adds or changes an
# entry must add it here too — that is the point: the diff shows both.
ALLOWED_PERMISSIONS = {
    "Bash(python scripts/fetch_jd.py:*)",
    "Bash(python3 scripts/fetch_jd.py:*)",
    "Bash(python scripts/fetch_jobs_batch.py:*)",
    "Bash(python3 scripts/fetch_jobs_batch.py:*)",
    "Bash(python scripts/fetch_jobs_multi_board.py:*)",
    "Bash(python3 scripts/fetch_jobs_multi_board.py:*)",
    "Bash(python scripts/fetch_jobs_multi_linkedin.py:*)",
    "Bash(python3 scripts/fetch_jobs_multi_linkedin.py:*)",
    "Bash(python scripts/fetch_jobs_multi_workday.py:*)",
    "Bash(python3 scripts/fetch_jobs_multi_workday.py:*)",
    "Bash(python scripts/fetch_jobs_linkedin_search.py:*)",
    "Bash(python3 scripts/fetch_jobs_linkedin_search.py:*)",
    "Bash(python scripts/fetch_jobs_workday_board.py:*)",
    "Bash(python3 scripts/fetch_jobs_workday_board.py:*)",
    "Bash(python scripts/build_daily_shortlist.py:*)",
    "Bash(python3 scripts/build_daily_shortlist.py:*)",
    "Bash(python scripts/add_manual_job.py:*)",
    "Bash(python3 scripts/add_manual_job.py:*)",
    "Bash(python scripts/run_decision_agent.py:*)",
    "Bash(python3 scripts/run_decision_agent.py:*)",
    "Bash(python scripts/run_decisions_for_new_jobs.py:*)",
    "Bash(python3 scripts/run_decisions_for_new_jobs.py:*)",
    "Bash(python scripts/prepare_application_draft.py:*)",
    "Bash(python3 scripts/prepare_application_draft.py:*)",
    "Bash(python scripts/finalize_application.py:*)",
    "Bash(python3 scripts/finalize_application.py:*)",
    "Bash(python scripts/mark_sent.py:*)",
    "Bash(python3 scripts/mark_sent.py:*)",
    "Bash(python scripts/run_selection_plan.py:*)",
    "Bash(python3 scripts/run_selection_plan.py:*)",
    "Bash(python scripts/run_watchlist_cv.py:*)",
    "Bash(python3 scripts/run_watchlist_cv.py:*)",
    "Bash(pytest:*)",
    "Bash(uvicorn backend.main:app:*)",
}

# Personal-data ignore rules that must never disappear from .gitignore.
REQUIRED_IGNORE_RULES = [
    "/domain/assets/",
    "/output/",
    "/out/",
    "/applications/",
    "/cv-output/",
    "/profiles/*",
    ".env",
    ".env.*",
    "credentials.json",
    "secrets/",
    "**/secrets/",
]

# Negation (re-include) rules this repo legitimately ships. .gitignore is
# order-sensitive: a later `!pattern` re-includes a path an earlier rule
# excluded, so a rule can be physically present in REQUIRED_IGNORE_RULES yet
# no longer ignored (e.g. adding `!.env`). Set membership on the required
# rules cannot see that. Any negation outside this allowlist is a failure —
# add an intentional one here in the same PR, exactly as with
# ALLOWED_PERMISSIONS, so the widening is explicit and reviewable.
ALLOWED_IGNORE_NEGATIONS = {
    "!.env.example",
    "!/profiles/.gitkeep",
}

# Hook commands this repo legitimately ships, as "<Event>:<command>" strings.
# Empty by design — this repo ships no hooks at all.
ALLOWED_HOOKS: set[str] = set()


def _hook_commands(event: str, entries: object):
    """Yield "<Event>:<command>" for every command a hook event would run.

    Fails closed: any shape this does not recognise yields a marker that
    cannot be in the allowlist, so an unfamiliar hook layout is rejected
    rather than silently skipped.
    """
    unrecognised = f"{event}:<unrecognised hook shape>"
    if not isinstance(entries, list):
        yield unrecognised
        return
    for entry in entries:
        if not isinstance(entry, dict):
            yield unrecognised
            continue
        inner = entry.get("hooks")
        if not isinstance(inner, list):
            yield unrecognised
            continue
        for hook in inner:
            command = hook.get("command") if isinstance(hook, dict) else None
            yield f"{event}:{command}" if isinstance(command, str) else unrecognised


def check_permissions() -> None:
    path = ROOT / ".claude" / "settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f".claude/settings.json: unreadable or invalid JSON: {exc}")
        return
    if not isinstance(data, dict):
        errors.append(".claude/settings.json: top-level JSON value must be an object")
        return

    # Checked before the permissions shape guards below, so a file that pairs
    # a malformed permissions block with a hook cannot return early and skip
    # this.
    hooks = data.get("hooks", {})
    if hooks:
        if not isinstance(hooks, dict):
            errors.append(".claude/settings.json: hooks must be an object")
        else:
            for event, entries in hooks.items():
                for command in _hook_commands(str(event), entries):
                    if command not in ALLOWED_HOOKS:
                        errors.append(
                            ".claude/settings.json: hook not in the reviewed "
                            f"allowlist: {command!r}. A hook runs automatically "
                            "when its event fires — it is never gated by the "
                            "permissions prompt, so it executes on every fork "
                            "without the user agreeing to anything. If this hook "
                            "is intentional, add it to ALLOWED_HOOKS in "
                            "tools/security_guards.py in the same PR so the "
                            "addition is explicit and reviewable."
                        )

    permissions = data.get("permissions", {})
    if not isinstance(permissions, dict):
        errors.append(".claude/settings.json: permissions must be an object")
        return
    allow = permissions.get("allow", [])
    if not isinstance(allow, list) or not all(isinstance(entry, str) for entry in allow):
        errors.append(".claude/settings.json: permissions.allow must be a list of strings")
        return
    for entry in allow:
        if entry not in ALLOWED_PERMISSIONS:
            errors.append(
                f".claude/settings.json: permission not in the reviewed allowlist: {entry!r}. "
                "Pre-approved permissions run without prompting on every fork. If this entry is "
                "intentional, add it to ALLOWED_PERMISSIONS in tools/security_guards.py in the "
                "same PR so the widening is explicit and reviewable."
            )
    for entry in ALLOWED_PERMISSIONS - set(allow):
        # Not an error: settings may legitimately drop an entry. But an
        # allowlist entry that no longer exists should be pruned.
        print(f"note: allowlisted permission not present in settings.json: {entry!r}")


def check_gitignore() -> None:
    path = ROOT / ".gitignore"
    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    except OSError as exc:
        errors.append(f".gitignore: unreadable: {exc}")
        return
    rules = set(lines)
    for rule in REQUIRED_IGNORE_RULES:
        if rule not in rules:
            errors.append(
                f".gitignore: required personal-data rule missing: {rule!r}. "
                "These rules keep fork users from committing personal data. If the rule moved "
                "or was renamed intentionally, update REQUIRED_IGNORE_RULES in "
                "tools/security_guards.py in the same PR."
            )
    for line in lines:
        if line.startswith("!") and line not in ALLOWED_IGNORE_NEGATIONS:
            errors.append(
                f".gitignore: negation rule not in the reviewed allowlist: {line!r}. "
                "A negation re-includes a path an earlier rule excluded and can silently "
                "re-expose personal data (a required ignore rule stays present but stops "
                "taking effect). If this negation is intentional, add it to "
                "ALLOWED_IGNORE_NEGATIONS in tools/security_guards.py in the same PR."
            )


def main() -> int:
    check_permissions()
    check_gitignore()
    if errors:
        print(f"security_guards: {len(errors)} failure(s)")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("security_guards: OK (permissions allowlist, hooks allowlist, gitignore rules)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
