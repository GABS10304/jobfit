"""Manage open topics — JD requirements not yet covered by the Master-CV.

The daily shortlist asks about these (backend/sourcing/open_topics.py).
After Gabby answers in chat, Claude adds the evidence to domain/cv_master.yaml
and marks the topic answered here; "no experience" stops the question.

Usage:
  python scripts/open_topics.py list                 # open topics, most requested first
  python scripts/open_topics.py list --all
  python scripts/open_topics.py answer evals --note "RIWANEXIS eval set, 2026"
  python scripts/open_topics.py none figma
  python scripts/open_topics.py reopen figma
  python scripts/open_topics.py check --jd-file jd.txt   # open topics for one JD
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.sourcing import open_topics as ot  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    lst = sub.add_parser("list")
    lst.add_argument("--all", action="store_true", help="Include answered / no_experience")
    for name in ("answer", "none", "reopen"):
        cmd = sub.add_parser(name)
        cmd.add_argument("topic_id")
        cmd.add_argument("--note", default=None)
    chk = sub.add_parser("check")
    chk.add_argument("--jd-file", type=Path, required=True)
    args = parser.parse_args()

    if args.cmd == "list":
        backlog = ot.load_backlog()
        rows = (sorted(backlog.items(), key=lambda i: (-int(i[1].get("count") or 0), i[0]))
                if args.all else ot.open_topics_ranked(backlog))
        if not rows:
            print("Keine offenen Themen.")
            return 0
        for topic_id, entry in rows:
            status = entry.get("status", ot.STATUS_OPEN)
            print(f"{int(entry.get('count') or 0):>3}x  {topic_id:<22} [{status}] "
                  f"{entry.get('label')} — {entry.get('question')}")
        return 0

    if args.cmd == "check":
        topics = ot.find_open_topics(args.jd_file.read_text(encoding="utf-8"))
        backlog = ot.load_backlog()
        for topic in topics:
            flag = " (schon beantwortet/abgelehnt)" if ot.is_suppressed(topic.id, backlog) else ""
            print(f"- {topic.id}: {topic.question}{flag}")
        if not topics:
            print("Keine offenen Themen – alles, was die JD fordert, steht im Master-CV.")
        return 0

    status = {"answer": ot.STATUS_ANSWERED, "none": ot.STATUS_NO_EXPERIENCE,
              "reopen": ot.STATUS_OPEN}[args.cmd]
    try:
        entry = ot.set_status(args.topic_id, status, note=args.note)
    except (KeyError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"{args.topic_id}: {entry['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
