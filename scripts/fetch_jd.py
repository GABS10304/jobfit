"""Fetch a Personio job posting and optionally run V3 fit-check.

Usage:
  python scripts/fetch_jd.py --url https://example.jobs.personio.de/job/123456
  python scripts/fetch_jd.py --url <personio_url> --fit-check
  python scripts/fetch_jd.py --url <personio_url> --fit-check --out /tmp/jd.json

Filter contract: exclude no_go; require min_top_score, product top role, no title deny keywords.
See domain/sourcing_filter.yaml.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend import data_loader, fit_engine
from backend.sourcing.filtering import (
    FILTER_PATH,
    evaluate_default_filter,
    fit_check_jd_text,
    top_fit_score,
)
from backend.sourcing.personio import fetch_personio_job


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Personio JD JSON and optionally run fit-check.",
        epilog=(
            "Filter contract: no_go excluded; min_top_score + product role + title deny "
            f"({FILTER_PATH.relative_to(REPO_ROOT)})."
        ),
    )
    parser.add_argument("--url", required=True, help="Personio job URL (*.jobs.personio.*/job/*)")
    parser.add_argument(
        "--fit-check",
        action="store_true",
        help="Run existing V3 fit-check on fetched JD text",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write normalized JD JSON to this path",
    )
    parser.add_argument(
        "--playwright",
        action="store_true",
        help="Force Playwright fetch fallback (requires playwright install)",
    )
    args = parser.parse_args()

    job = fetch_personio_job(args.url, use_playwright=args.playwright)
    payload = job.to_dict()

    print(f"title: {job.title}")
    print(f"location: {job.location or '-'}")
    print(f"work_mode: {job.work_mode or '-'}")
    print(f"employment_type: {job.employment_type or '-'}")
    print(f"source: {job.source}")
    print(f"fetched_at: {job.fetched_at}")
    print(f"jd_text_chars: {len(job.jd_text)}")

    if args.fit_check:
        profile = data_loader.load_role_fit_profile()
        constraints = data_loader.load_constraints()
        fit = fit_engine.run_fit_check(
            job_description=fit_check_jd_text(job),
            profile=profile,
            constraints=constraints,
        )
        top_score, top_role = top_fit_score(fit)
        passes, reject_reason = evaluate_default_filter(
            fit.status_flag,
            top_score=top_score,
            top_role_id=top_role,
            title=job.title,
        )
        fit_payload = {
            "status_flag": fit.status_flag,
            "verify_product_ownership": fit.verify_product_ownership,
            "presence_policy": fit.presence_policy.model_dump(),
            "top_score": top_score,
            "top_role_id": top_role,
            "passes_default_filter": passes,
        }
        if reject_reason:
            fit_payload["filter_reject_reason"] = reject_reason
        payload["fit_check"] = fit_payload
        print(f"status_flag: {fit.status_flag}")
        print(f"presence: {fit.presence_policy.level} / {fit.presence_policy.outcome}")
        print(f"top_score: {top_score if top_score is not None else '-'}")
        print(f"passes_default_filter: {passes}")
        if reject_reason:
            print(f"filter_reject_reason: {reject_reason}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"written: {args.out}")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
