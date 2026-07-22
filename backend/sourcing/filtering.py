"""Default sourcing filter contract and fit-check helpers."""

from __future__ import annotations

from pathlib import Path

import yaml

from backend.sourcing.personio import NormalizedJobDescription

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FILTER_PATH = REPO_ROOT / "domain" / "sourcing_filter.yaml"


def load_filter_contract() -> dict:
    with FILTER_PATH.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def passes_default_filter(status_flag: str) -> bool:
    contract = load_filter_contract()
    default_pass = contract.get("default_pass", {})
    excluded = set(default_pass.get("exclude_status_flags", ["no_go"]))
    included = set(
        default_pass.get(
            "include_status_flags",
            ["proceed", "verify_product_ownership"],
        )
    )
    if status_flag in excluded:
        return False
    return status_flag in included


def fit_check_jd_text(job: NormalizedJobDescription) -> str:
    parts = [job.title]
    if job.location:
        parts.append(job.location)
    if job.work_mode and job.work_mode.casefold() not in (job.location or "").casefold():
        parts.append(job.work_mode)
    if job.employment_type:
        parts.append(job.employment_type)
    parts.append(job.jd_text)
    return "\n\n".join(parts)


def top_fit_score(fit) -> tuple[int | None, str | None]:
    candidates = fit.results or fit.excluded_roles
    if not candidates:
        return None, None
    top = max(candidates, key=lambda role: role.score)
    return top.score, top.role_id
