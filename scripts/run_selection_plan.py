"""Run deterministic selection_plan (+ optional CV render) against a JD.

Usage:
  python scripts/run_selection_plan.py
  python scripts/run_selection_plan.py --jd-inline --render
  python scripts/run_selection_plan.py --jd-inline --render --out /tmp/cv_variant.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend import data_loader, fit_engine
from backend.generation.cv_variant import generate_cv_variant
from backend.generation.selection_plan import selection_plan
from backend.models import CvVariant

DEFAULT_FIXTURE = (
    REPO_ROOT
    / "domain"
    / "fixtures"
    / "ops_teamviewer_ai_product_discovery_hybrid.yaml"
)

FLEX_LIKE_JD = (
    "Remote / hybrid AI Product Manager for B2B SaaS. "
    "Product ownership, product discovery, AI use case validation, "
    "customer feedback, stakeholder management, change management, "
    "requirements engineering, data driven decision making. "
    "Stack: Python, SQL, Jira, Confluence."
)


def _load_jd_from_fixture(path: Path) -> str:
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict) or "job_description" not in raw:
        raise ValueError(f"Fixture missing job_description: {path}")
    return str(raw["job_description"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CV selection_plan MVP")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="YAML fixture with job_description",
    )
    parser.add_argument(
        "--jd-inline",
        action="store_true",
        help="Use built-in FLEX-like JD instead of fixture",
    )
    parser.add_argument(
        "--role-ids",
        nargs="*",
        default=None,
        help="Optional role_ids subset for fit-check",
    )
    parser.add_argument(
        "--render",
        action="store_true",
        help="Also print ATS-friendly CV markdown from selection_plan",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write rendered CV markdown to this path (implies --render)",
    )
    args = parser.parse_args()

    jd = FLEX_LIKE_JD if args.jd_inline else _load_jd_from_fixture(args.fixture)
    cv = data_loader.load_cv_master()
    profile = data_loader.load_role_fit_profile()
    constraints = data_loader.load_constraints()
    rules = data_loader.load_cv_rules()

    fit = fit_engine.run_fit_check(
        job_description=jd,
        profile=profile,
        constraints=constraints,
        role_ids=args.role_ids,
    )
    plan = selection_plan(cv, profile, fit, jd, rules)
    variant = CvVariant(
        selection_plan=plan,
        language=rules.language.default,
        section_order=list(rules.section_order),
        max_pages_hint=rules.limits.max_total_pages_hint,
    )
    print(json.dumps(variant.model_dump(), ensure_ascii=False, indent=2))

    if args.render or args.out is not None:
        rendered = generate_cv_variant(plan, cv, rules)
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(rendered, encoding="utf-8")
            print(f"\n--- CV written to {args.out} ---", file=sys.stderr)
        print("\n--- CV (ATS markdown) ---\n")
        print(rendered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
