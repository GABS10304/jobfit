"""Salary forecast for one job (stated figure from the JD, else band estimate).

Usage:
  python scripts/salary_estimate.py --title "Senior Product Manager" --location München --jd-file jd.txt
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend import data_loader  # noqa: E402
from backend.sourcing.salary_estimate import estimate_salary  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--title", required=True)
    parser.add_argument("--location", default=None)
    parser.add_argument("--jd-file", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    jd = args.jd_file.read_text(encoding="utf-8") if args.jd_file else ""
    comp = data_loader.load_constraints().compensation
    est = estimate_salary(title=args.title, jd_text=jd, location=args.location,
                          min_annual_base=comp.min_annual_base if comp else None)
    print(json.dumps(est.to_dict(), ensure_ascii=False, indent=2) if args.json else est.label())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
