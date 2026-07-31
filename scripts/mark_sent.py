"""Record that a finalized application was actually submitted.

job-fit-system never auto-applies — Gabriel submits the PDF himself on the
job portal. This just records that it happened, so the daily digest and
state store stop treating the job as an open draft.

Usage:
  python scripts/mark_sent.py --job-id 2689046_ai-product-manager-m-w-d
  python scripts/mark_sent.py --job-id 2689046_ai-product-manager-m-w-d --date 20260731
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.tracking import state_store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--date", default=None, help="YYYYMMDD, defaults to today (UTC)")
    args = parser.parse_args()

    try:
        entry = state_store.get_entry(args.job_id)
        if entry is None:
            raise KeyError(f"Unknown job_id (not in state store): {args.job_id}")
        if entry.get("status") != state_store.STATUS_FINALIZED:
            print(
                f"Hinweis: Status war '{entry.get('status')}', nicht 'finalized' — "
                "wird trotzdem als gesendet markiert.",
                file=sys.stderr,
            )
        updated = state_store.mark_sent(args.job_id, sent_date=args.date)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"{args.job_id}: status=sent, sent_at={updated['sent_at']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
