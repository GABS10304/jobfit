"""Approval step: "ja zu <job_id>" → build the CV draft + context for the cover letter.

Loads the job row from state_store + its source artifact, runs the existing
deterministic selection_plan/generate_cv_variant/generate_cv_variant_pdf
pipeline (unchanged), and writes:

  out/review/<job_id>/cv.md
  out/review/<job_id>/cv.pdf
  out/review/<job_id>/context.json   ← facts for Claude to write the Anschreiben from

The cover letter text itself is NOT generated here — per the agreed design,
Claude writes it live in the approval chat from context.json + domain/cv_master.yaml
+ the cv-tailor style rules, then saves out/review/<job_id>/anschreiben.md for
scripts/finalize_application.py to combine into the final PDF.

Usage:
  python scripts/prepare_application_draft.py --job-id 2544351_senior-product-manager-m-w-d
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend import data_loader, fit_engine  # noqa: E402
from backend.generation.cv_pdf import generate_cv_variant_pdf  # noqa: E402
from backend.generation.cv_translate_service import translate_cv_markdown  # noqa: E402
from backend.generation.cv_variant import generate_cv_variant  # noqa: E402
from backend.generation.selection_plan import selection_plan  # noqa: E402
from backend.generation.watchlist_cv import jd_text_from_job_dict  # noqa: E402
from backend.sourcing.contact_extract import extract_hiring_contact  # noqa: E402
from backend.sourcing.language_detect import detect_jd_language  # noqa: E402
from backend.tracking import state_store  # noqa: E402

DEFAULT_REVIEW_DIR = REPO_ROOT / "out" / "review"


def _find_row(artifact_path: Path, url: str) -> dict[str, Any]:
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    for bucket in ("passed", "watchlist"):
        for row in payload.get(bucket) or []:
            row_url = row.get("url") or (row.get("job") or {}).get("url")
            if row_url == url:
                return row
    raise ValueError(f"job url not found in {artifact_path}: {url}")


def build_context(job_id: str) -> dict[str, Any]:
    """Compute the facts context for a job — no file writes, no state
    transitions, no CV translation (that's only needed for the final
    rendered artifact, not for reasoning about the job). Shared by
    build_draft() and scripts/run_decision_agent.py, which needs these
    facts *before* deciding whether a draft is even worth building.
    """
    entry = state_store.get_entry(job_id)
    if entry is None:
        raise KeyError(f"Unknown job_id (not in state store): {job_id}")

    row = _find_row(Path(entry["source_artifact"]), entry["url"])
    job = row.get("job") or {}
    jd_text = jd_text_from_job_dict(job)

    cv_master = data_loader.load_cv_master()
    role_fit_profile = data_loader.load_role_fit_profile()
    constraints = data_loader.load_constraints()
    cv_rules = data_loader.load_cv_rules()

    fit = fit_engine.run_fit_check(
        job_description=jd_text,
        profile=role_fit_profile,
        constraints=constraints,
    )
    plan = selection_plan(cv_master, role_fit_profile, fit, jd_text, cv_rules)
    cv_markdown = generate_cv_variant(plan, cv_master, cv_rules)
    top = fit.results[0] if fit.results else (fit.excluded_roles[0] if fit.excluded_roles else None)

    return {
        "job_id": job_id,
        "title": entry.get("title") or job.get("title"),
        "company": entry.get("company"),
        "url": entry.get("url"),
        "jd_text": jd_text,
        "hiring_contact": extract_hiring_contact(jd_text),
        "location_match": entry.get("location_match"),
        "role_id": plan.selected_role_id,
        "role_name": plan.selected_role_name,
        "role_score": plan.role_score,
        "matched_signals": top.matched_signals if top else [],
        "missing_signals": top.missing_signals if top else [],
        "selection_rationale": plan.rationale,
        "selection_explain": plan.explain,
        "person_name": cv_master.person.name,
        "person_location": cv_master.person.location,
        "impact_notes": constraints.impact_notes,
        "cv_markdown": cv_markdown,
    }


def build_draft(job_id: str, *, review_dir: Path = DEFAULT_REVIEW_DIR) -> Path:
    context = build_context(job_id)
    jd_text = context["jd_text"]
    cv_markdown = context["cv_markdown"]

    language = detect_jd_language(jd_text)
    cv_markdown_rendered = cv_markdown
    if language == "en":
        try:
            cv_markdown_rendered = translate_cv_markdown(cv_markdown)
        except Exception as exc:  # noqa: BLE001 - fail open, see comment below
            # An English-JD application shouldn't be blocked by a missing API
            # key / refusal / transient error — fall back to the German CV
            # and flag it loudly instead of failing silently. Deliberately
            # broad: missing credentials raise a plain TypeError from the
            # anthropic client, not one of our typed exceptions.
            print(
                f"WARNUNG: CV-Übersetzung ins Englische fehlgeschlagen ({exc}); "
                "verwende deutschen CV-Text.",
                file=sys.stderr,
            )
            language = "de"
            cv_markdown_rendered = cv_markdown

    out_dir = review_dir / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    cv_path = out_dir / "cv.md"
    cv_path.write_text(cv_markdown_rendered, encoding="utf-8")
    generate_cv_variant_pdf(cv_markdown_rendered, out_dir / "cv.pdf")

    context["language"] = language
    context["cv_markdown"] = cv_markdown_rendered
    context["cv_markdown_de"] = cv_markdown
    (out_dir / "context.json").write_text(
        json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    state_store.mark_status(job_id, state_store.STATUS_APPROVED)
    state_store.mark_status(job_id, state_store.STATUS_DRAFT_READY)

    return out_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--review-dir", type=Path, default=DEFAULT_REVIEW_DIR)
    args = parser.parse_args()

    try:
        out_dir = build_draft(args.job_id, review_dir=args.review_dir)
    except (KeyError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"draft written: {out_dir}")
    print("  cv.md, cv.pdf, context.json")

    context = json.loads((out_dir / "context.json").read_text(encoding="utf-8"))
    contact = context.get("hiring_contact") or {}
    if contact.get("name") or contact.get("email"):
        print(f"📇 hiring contact found: {contact.get('name') or '?'} <{contact.get('email') or '?'}>")

    print("Next: write out/review/<job_id>/anschreiben.md, then run finalize_application.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
