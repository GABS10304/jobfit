"""Render weak-match CV variants from a batch watchlist JSON.

Usage:
  python scripts/run_watchlist_cv.py --from-json /tmp/flex_e2e_watchlist.json
  python scripts/run_watchlist_cv.py --from-json results.json --cv-out out/cv_watchlist
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.generation.watchlist_cv import write_watchlist_cvs


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate labeled weak-match CV markdown from sourcing watchlist "
            "rows (batch JSON). Does not lower the strong-match bar."
        ),
    )
    parser.add_argument(
        "--from-json",
        type=Path,
        required=True,
        help="Batch results JSON with a watchlist array (from --include-weak-proceed)",
    )
    parser.add_argument(
        "--cv-out",
        type=Path,
        default=Path("out/cv_watchlist"),
        help="Directory for weak-match CV markdown (default: out/cv_watchlist)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Write at most N watchlist CVs",
    )
    args = parser.parse_args()

    payload = json.loads(args.from_json.read_text(encoding="utf-8"))
    watchlist = list(payload.get("watchlist") or [])
    if not watchlist:
        print(
            f"No watchlist entries in {args.from_json} "
            "(run batch with --include-weak-proceed).",
            file=sys.stderr,
        )
        return 1

    if args.limit is not None:
        watchlist = watchlist[: args.limit]

    written = write_watchlist_cvs(watchlist, args.cv_out)
    print(f"watchlist CVs written: {len(written)} → {args.cv_out}")
    for path in written:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
