"""Human-in-the-loop step: "passt" → combine reviewed draft into the final PDF.

Reads out/review/<job_id>/anschreiben.md (written by Claude in the approval
chat, possibly hand-edited by the user) + cv.md (from prepare_application_draft.py),
combines them into one PDF via backend.generation.application_pdf, and writes
it to out/applications_ready/<job_id>/.

Usage:
  python scripts/finalize_application.py --job-id 2544351_senior-product-manager-m-w-d
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.generation.application_pdf import generate_application_pdf  # noqa: E402
from backend.tracking import state_store  # noqa: E402

DEFAULT_REVIEW_DIR = REPO_ROOT / "out" / "review"
DEFAULT_APPLICATIONS_DIR = REPO_ROOT / "out" / "applications_ready"

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str | None) -> str:
    raw = (text or "").casefold().strip()
    slug = _SLUG_RE.sub("-", raw).strip("-")
    return slug or "job"


def finalize(
    job_id: str,
    *,
    review_dir: Path = DEFAULT_REVIEW_DIR,
    applications_dir: Path = DEFAULT_APPLICATIONS_DIR,
) -> Path:
    entry = state_store.get_entry(job_id)
    if entry is None:
        raise KeyError(f"Unknown job_id (not in state store): {job_id}")

    draft_dir = review_dir / job_id
    cover_letter_path = draft_dir / "anschreiben.md"
    cv_path = draft_dir / "cv.md"
    if not cover_letter_path.exists():
        raise FileNotFoundError(
            f"Missing {cover_letter_path} — write the Anschreiben first (see "
            "prepare_application_draft.py output / context.json)."
        )
    if not cv_path.exists():
        raise FileNotFoundError(f"Missing {cv_path} — run prepare_application_draft.py first.")

    cover_letter_text = cover_letter_path.read_text(encoding="utf-8")
    cv_text = cv_path.read_text(encoding="utf-8")

    company_slug = _slugify(entry.get("company"))
    role_slug = _slugify(entry.get("title"))
    date_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = applications_dir / job_id
    out_path = out_dir / f"Bewerbung_{company_slug}_{role_slug}_{date_stamp}.pdf"

    generate_application_pdf(cover_letter_text, cv_text, out_path)
    state_store.mark_status(job_id, state_store.STATUS_FINALIZED)

    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--review-dir", type=Path, default=DEFAULT_REVIEW_DIR)
    parser.add_argument("--applications-dir", type=Path, default=DEFAULT_APPLICATIONS_DIR)
    args = parser.parse_args()

    try:
        out_path = finalize(
            args.job_id, review_dir=args.review_dir, applications_dir=args.applications_dir
        )
    except (KeyError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"final application PDF: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
