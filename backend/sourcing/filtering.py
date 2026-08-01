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


def _is_product_role(role_id: str | None, default_pass: dict) -> bool:
    if not role_id:
        return False
    role_cf = role_id.casefold()
    allowlist = {str(r).casefold() for r in default_pass.get("product_role_ids") or []}
    if role_cf in allowlist:
        return True
    substrings = [
        str(s).casefold()
        for s in default_pass.get("product_role_id_substrings") or ["product"]
    ]
    return any(sub and sub in role_cf for sub in substrings)


def is_excluded_company(name: str | None, excluded: list[str] | None) -> bool:
    """Case-insensitive exact-name match against constraints.excluded_companies."""
    if not name or not excluded:
        return False
    name_cf = name.casefold().strip()
    return any(name_cf == str(entry).casefold().strip() for entry in excluded if entry)


_LOCATION_SYNONYMS: dict[str, tuple[str, ...]] = {
    "remote": ("remote", "home office", "homeoffice", "work from anywhere"),
    "germany": ("germany", "deutschland"),
    "dach": (
        "dach", "germany", "deutschland", "austria", "österreich",
        "switzerland", "schweiz",
    ),
}


def _location_cue_candidates(label: str) -> tuple[str, ...]:
    key = label.strip().casefold()
    return _LOCATION_SYNONYMS.get(key, (key,))


def evaluate_location_fit(jd_text: str, location_preferences) -> dict:
    """Advisory-only location signal against constraints.location_preferences.

    Deliberately never touches the fit score or the pass/watchlist gates —
    those stay pure content-fit (see role_fit_profile.yaml signal matching).
    This only flags "outside_preferred" so the shortlist/manual-add output
    can surface a relocation-willingness note on otherwise-strong matches,
    instead of a job just quietly scoring the same either way.
    """
    if location_preferences is None:
        return {"match": "unknown", "note": None}

    text = (jd_text or "").casefold()

    for avoid in location_preferences.avoid_locations or []:
        if any(cue in text for cue in _location_cue_candidates(avoid)):
            return {"match": "avoid", "note": f"JD nennt vermiedenen Standort ({avoid})."}

    for preferred in location_preferences.preferred_locations or []:
        if any(cue in text for cue in _location_cue_candidates(preferred)):
            return {"match": "preferred", "note": None}

    return {
        "match": "outside_preferred",
        "note": "Standort nicht in den bevorzugten Standorten (preferred_locations) gefunden.",
    }


# Below this, a location mismatch isn't the interesting story anymore — the
# content-fit itself is already weak. Above it, worth flagging relocation as
# an option rather than letting a solid match blend in with the rest.
RELOCATION_NOTE_MIN_SCORE = 50


def relocation_note(top_score: int | None, location_match: str | None) -> str | None:
    """Advisory text for a solid-scoring job outside preferred locations."""
    if location_match not in ("outside_preferred", "avoid"):
        return None
    if top_score is None or top_score < RELOCATION_NOTE_MIN_SCORE:
        return None
    return (
        "Standort außerhalb der Präferenzen, aber Score solide — trotzdem "
        "vorschlagen: Umzugsbereitschaft, wenn der Job wirklich gut ist."
    )


def _keyword_hit(title: str | None, keywords: list | None) -> str | None:
    if not title:
        return None
    title_cf = title.casefold()
    for raw in keywords or []:
        keyword = str(raw).casefold().strip()
        if keyword and keyword in title_cf:
            return keyword
    return None


def _title_denied(title: str | None, default_pass: dict) -> str | None:
    return _keyword_hit(title, default_pass.get("title_deny_keywords"))


def _prefilter_deny_keywords(contract: dict) -> list:
    prefilter = contract.get("title_prefilter") or {}
    override = prefilter.get("deny_keywords") or []
    if override:
        return list(override)
    default_pass = contract.get("default_pass") or {}
    return list(default_pass.get("title_deny_keywords") or [])


def evaluate_title_prefilter(title: str | None) -> tuple[bool, str | None]:
    """Title gate before fit-check. Returns (passes, reject_reason).

    Deny first (e.g. product marketing), then allow_keywords, then product_keywords.
    """
    contract = load_filter_contract()
    prefilter = contract.get("title_prefilter") or {}
    if not prefilter.get("enabled", True):
        return True, None

    if not title or not str(title).strip():
        return False, "title_prefilter:missing_title"

    deny_hit = _keyword_hit(title, _prefilter_deny_keywords(contract))
    if deny_hit:
        return False, f"title_prefilter:deny={deny_hit}"

    allow_hit = _keyword_hit(title, prefilter.get("allow_keywords"))
    if allow_hit:
        return True, None

    product_hit = _keyword_hit(title, prefilter.get("product_keywords"))
    if product_hit:
        return True, None

    return False, "title_prefilter:no_allow_or_product_keyword"


def _status_and_title_gates(
    status_flag: str,
    *,
    top_role_id: str | None,
    title: str | None,
    default_pass: dict,
) -> tuple[bool, str | None]:
    """Shared gates for strong pass and weak watchlist (excludes score)."""
    excluded = set(default_pass.get("exclude_status_flags", ["no_go"]))
    included = set(
        default_pass.get(
            "include_status_flags",
            ["proceed", "verify_product_ownership"],
        )
    )

    if status_flag in excluded:
        return False, f"status_flag={status_flag}"
    if status_flag not in included:
        return False, f"status_flag={status_flag}"

    denied_kw = _title_denied(title, default_pass)
    if denied_kw:
        return False, f"title_deny_keyword={denied_kw}"

    if default_pass.get("require_product_role", True):
        if not _is_product_role(top_role_id, default_pass):
            role_text = top_role_id or "none"
            return False, f"top_role_not_product={role_text}"

    return True, None


def evaluate_default_filter(
    status_flag: str,
    *,
    top_score: int | None = None,
    top_role_id: str | None = None,
    title: str | None = None,
) -> tuple[bool, str | None]:
    """Apply sourcing_filter.yaml; return (passes, reject_reason)."""
    contract = load_filter_contract()
    default_pass = contract.get("default_pass", {})

    ok, reason = _status_and_title_gates(
        status_flag,
        top_role_id=top_role_id,
        title=title,
        default_pass=default_pass,
    )
    if not ok:
        return False, reason

    min_top_score = int(default_pass.get("min_top_score", 75))
    if top_score is None or top_score < min_top_score:
        score_text = "none" if top_score is None else str(top_score)
        return False, f"top_score={score_text}<{min_top_score}"

    return True, None


def evaluate_watchlist(
    status_flag: str,
    *,
    top_score: int | None = None,
    top_role_id: str | None = None,
    title: str | None = None,
) -> tuple[bool, str | None]:
    """Weak product match below min_top_score; never counts as passed.

    Eligible when status/title/product gates pass and score is present but
    below the strong-match bar (default 75). Rejected roles (e.g. no_go) stay out.
    """
    contract = load_filter_contract()
    default_pass = contract.get("default_pass", {})
    watchlist = contract.get("watchlist") or {}
    if not watchlist.get("enabled", True):
        return False, "watchlist_disabled"

    ok, reason = _status_and_title_gates(
        status_flag,
        top_role_id=top_role_id,
        title=title,
        default_pass=default_pass,
    )
    if not ok:
        return False, reason

    min_top_score = int(default_pass.get("min_top_score", 75))
    if top_score is None:
        return False, f"top_score=none<{min_top_score}"
    if top_score >= min_top_score:
        return False, f"top_score={top_score}>={min_top_score}"

    return True, f"weak_score={top_score}<{min_top_score}"


def passes_default_filter(
    status_flag: str,
    *,
    top_score: int | None = None,
    top_role_id: str | None = None,
    title: str | None = None,
) -> bool:
    passes, _ = evaluate_default_filter(
        status_flag,
        top_score=top_score,
        top_role_id=top_role_id,
        title=title,
    )
    return passes


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
