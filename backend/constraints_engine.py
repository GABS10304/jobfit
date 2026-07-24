"""Constraints layer – hard gates before role-fit scoring.

Heuristic cue matching against the JD text only. No invented salary/location
facts. Unclear work-mode status → no-go (per constraints notes).

V3 presence policy:
- ≤1 office day / remote-first → passed
- 2–3 office days → penalty (exception decided after scoring in fit_engine)
- >3 days or feste Präsenzpflicht → failed / hard no-go
"""

from __future__ import annotations

from backend.models import (
    ConstraintCheckResult,
    Constraints,
    HardConstraint,
    HardConstraintResult,
    SoftConstraint,
    SoftConstraintResult,
)

# Cue lists are intentionally conservative and documented in FIT_LOGIC_NOTES.md.
# TODO: replace/extend with curated aliases once reviewed against real JDs.

# remote_first_hybrid_ok: up to 1 office day/week is OK.
_REMOTE_FIRST_OK = (
    "remote",
    "fully remote",
    "100% remote",
    "home office",
    "homeoffice",
    "hybrid",
    "remote-first",
    "remote first",
    "work from home",
    "wfh",
    "1 office day",
    "one office day",
    "1 day in the office",
    "1 tag im büro",
    "1 bürotag",
    "ein bürotag",
    "ein präsenztag",
    "1 präsenztag",
    "ein tag vor ort",
    "1 tag vor ort",
    "1 tag pro woche",
    "ein tag pro woche",
    "bis zu 1 tag",
    "bis zu einem tag",
    "max. 1 tag",
    "maximal 1 tag",
)

# V3: 2–3 Office-Tage → Penalty (Ausnahme nur bei außergewöhnlich starker Rolle).
# Include "Mal die Woche" (sipgate-style) and en-dash variants; casefold alone
# does not normalize "–" → "-".
_PRESENCE_PENALTY_2_TO_3 = (
    "2 tage büro",
    "2 days in the office",
    "2 office days",
    "two office days",
    "2 präsenztage",
    "zwei präsenztage",
    "2 tage vor ort",
    "zwei tage vor ort",
    "2 tage pro woche",
    "zwei tage pro woche",
    "2-3 tage pro woche",
    "2–3 tage pro woche",
    "2 bis 3 tage pro woche",
    "2 bürotage",
    "zwei bürotage",
    "3 tage büro",
    "3 days in the office",
    "3 office days",
    "three office days",
    "3 präsenztage",
    "drei präsenztage",
    "3 tage vor ort",
    "drei tage vor ort",
    "3 tage pro woche",
    "drei tage pro woche",
    "3 bürotage",
    "drei bürotage",
    # Frequency without "Tage" (e.g. "2–3 Mal die Woche am Campus")
    "2-3 mal die woche",
    "2–3 mal die woche",
    "2 bis 3 mal die woche",
    "zwei bis drei mal die woche",
)

# >3 days / feste Präsenzpflicht / predominantly onsite → hard no-go.
_PRESENCE_HARD_NO_GO = (
    "onsite only",
    "on-site only",
    "office only",
    "vor ort verpflichtend",
    "präsenzpflicht",
    "feste präsenz",
    "feste präsenzpflicht",
    "überwiegend vor ort",
    "überwiegend im büro",
    "überwiegend präsenz",
    "keine remote",
    "no remote",
    "must be onsite",
    "must be on-site",
    "4 tage büro",
    "4 days in the office",
    "4 office days",
    "4 präsenztage",
    "vier präsenztage",
    "4 tage pro woche",
    "vier tage pro woche",
    "5 tage büro",
    "5 days in office",
    "5 präsenztage",
    "full-time office",
    "full time in office",
)

_HARD_SALES = (
    "quota",
    "hunter",
    "cold calling",
    "kaltakquise",
    "account executive",
    "sales quota",
    "closing deals",
    "commission only",
    "reine vertriebsrolle",
)

_PRODUCT_OWNERSHIP = (
    "product owner",
    "product manager",
    "product lead",
    "head of product",
    "produktverantwortung",
    "product ownership",
    "own the roadmap",
    "owns the roadmap",
    "product responsibility",
    "ai product manager",
    "technical product manager",
)

# Clear anti-cues: not product-adjacent / no ownership.
# TODO: refine with real JD samples.
_NON_PRODUCT = (
    "pure project manager",
    "reine projektleitung",
    "admin pmo",
    "pure pmo",
    "ceremony-only",
    "ceremony only",
    "no product ownership",
    "ohne produktverantwortung",
    "keine produktverantwortung",
    "feature factory without discovery",
    "schedule-only delivery",
    "waterfall project manager",
)

_SOFT_CUES: dict[str, tuple[str, ...]] = {
    "b2b_preferred": ("b2b", "business-to-business", "saas", "enterprise"),
    "govtech_or_regulated_preferred": (
        "govtech",
        "public sector",
        "öffentlicher sektor",
        "regulated",
        "reguliert",
        "dsgvo",
        "gdpr",
        "compliance",
    ),
    "ai_or_data_preferred": (
        "artificial intelligence",
        " machine learning",
        " ai ",
        "llm",
        "data-driven",
        "data driven",
        "analytics",
        "bigquery",
        "rag",
    ),
    "team_coaching_preferred": (
        "agile coach",
        "team coaching",
        "team coach",
        "scrum master",
        "facilitation",
        "agile transformation",
        "coaching-mandat",
        "coaching mandat",
        "reine coaching-rolle",
    ),
}


def _normalize(text: str) -> str:
    return f" {text.casefold()} "


def _find_cues(jd: str, cues: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for cue in cues:
        needle = cue.casefold()
        if needle in jd:
            # Skip matches that only appear inside an explicit negation.
            # e.g. "ohne reine coaching-rolle" / "keine feste präsenzpflicht".
            negated = (
                f"ohne {needle}" in jd
                or f"keine {needle}" in jd
                or f"kein {needle}" in jd
                or f"ohne reine {needle}" in jd
                or f"ohne feste {needle}" in jd
                or f"keine feste {needle}" in jd
                or f"not a {needle}" in jd
                or f"no {needle}" in jd
            )
            if negated:
                continue
            found.append(cue)
    return found


def _eval_remote_first_hybrid_ok(
    constraint: HardConstraint, jd: str
) -> HardConstraintResult:
    """V3: ≤1 OK; 2–3 Tage = penalty; >3 / feste Pflicht = failed."""
    if not constraint.enabled:
        return HardConstraintResult(
            id=constraint.id,
            label=constraint.label,
            status="skipped",
            reason="Constraint disabled.",
        )

    ok = _find_cues(jd, _REMOTE_FIRST_OK)
    mid = _find_cues(jd, _PRESENCE_PENALTY_2_TO_3)
    hard_no = _find_cues(jd, _PRESENCE_HARD_NO_GO)

    # Hard presence always wins (inkl. Mischfälle mit remote/hybrid-Wording).
    if hard_no:
        return HardConstraintResult(
            id=constraint.id,
            label=constraint.label,
            status="failed",
            reason=(
                "JD signals >3 Office-Tage/Woche oder feste/überwiegende Präsenzpflicht "
                "ohne klaren Mehrwert → hartes No-Go."
            ),
            matched_cues=hard_no + mid + ok,
        )

    # 2–3 Office-Tage: Penalty – Ausnahme erst nach Scoring (explizit in Response).
    if mid:
        return HardConstraintResult(
            id=constraint.id,
            label=constraint.label,
            status="penalty",
            reason=(
                "JD signals 2–3 Office-Tage/Woche (Präsenz-Penalty). "
                "Nur akzeptabel bei außergewöhnlich starker Rolle; "
                "Ausnahme muss im Fit-Check explizit sichtbar sein."
            ),
            matched_cues=mid + ok,
        )

    if ok:
        return HardConstraintResult(
            id=constraint.id,
            label=constraint.label,
            status="passed",
            reason=(
                "JD supports remote-first or hybrid "
                "(bis zu 1 Office-Tag/Woche zulässig)."
            ),
            matched_cues=ok,
        )
    return HardConstraintResult(
        id=constraint.id,
        label=constraint.label,
        status="unclear",
        reason=(
            "Work mode (remote-first / hybrid / ≤1 office day) not explicit in JD. "
            "Per constraints notes: must be verified explicitly if unclear → no-go."
        ),
        matched_cues=[],
    )


def _eval_no_hard_sales(constraint: HardConstraint, jd: str) -> HardConstraintResult:
    if not constraint.enabled:
        return HardConstraintResult(
            id=constraint.id,
            label=constraint.label,
            status="skipped",
            reason="Constraint disabled.",
        )

    sales = _find_cues(jd, _HARD_SALES)
    product = _find_cues(jd, _PRODUCT_OWNERSHIP)

    if sales and not product:
        return HardConstraintResult(
            id=constraint.id,
            label=constraint.label,
            status="failed",
            reason="JD looks like hard sales / quota without product ownership cues.",
            matched_cues=sales,
        )
    if sales and product:
        return HardConstraintResult(
            id=constraint.id,
            label=constraint.label,
            status="passed",
            reason="Sales cues present, but product-ownership cues also found.",
            matched_cues=sales + product,
        )
    return HardConstraintResult(
        id=constraint.id,
        label=constraint.label,
        status="passed",
        reason="No hard-sales-only cues detected.",
        matched_cues=[],
    )


def _eval_product_ownership(
    constraint: HardConstraint, jd: str
) -> HardConstraintResult:
    if not constraint.enabled:
        return HardConstraintResult(
            id=constraint.id,
            label=constraint.label,
            status="skipped",
            reason="Constraint disabled.",
        )

    product = _find_cues(jd, _PRODUCT_OWNERSHIP)
    non_product = _find_cues(jd, _NON_PRODUCT)

    # Ignore "product …" cues that only appear inside a negative phrase
    # (e.g. "no product ownership" must not count as ownership).
    genuine_product = [
        p
        for p in product
        if not any(p.casefold() in n.casefold() for n in non_product)
    ]

    if genuine_product and not non_product:
        return HardConstraintResult(
            id=constraint.id,
            label=constraint.label,
            status="passed",
            reason="JD contains clear product-ownership cues.",
            matched_cues=genuine_product,
        )
    if genuine_product and non_product:
        return HardConstraintResult(
            id=constraint.id,
            label=constraint.label,
            status="unclear",
            reason=(
                "Mixed product and non-product cues – ownership only implicit/ambiguous. "
                "Manual verification recommended; scoring continues."
            ),
            matched_cues=genuine_product + non_product,
        )
    if non_product:
        return HardConstraintResult(
            id=constraint.id,
            label=constraint.label,
            status="failed",
            reason="JD signals no product ownership or a clearly non-product role.",
            matched_cues=non_product,
        )
    return HardConstraintResult(
        id=constraint.id,
        label=constraint.label,
        status="unclear",
        reason=(
            "Product ownership not explicit in JD (unclear or only implicit). "
            "Decision: verify_product_ownership – scoring continues."
        ),
        matched_cues=[],
    )


_HARD_EVALUATORS = {
    "remote_first_hybrid_ok": _eval_remote_first_hybrid_ok,
    "no_hard_sales": _eval_no_hard_sales,
    "product_ownership_required": _eval_product_ownership,
}


def _eval_hard(constraint: HardConstraint, jd: str) -> HardConstraintResult:
    evaluator = _HARD_EVALUATORS.get(constraint.id)
    if evaluator is None:
        return HardConstraintResult(
            id=constraint.id,
            label=constraint.label,
            status="unclear",
            reason=f"TODO: no evaluator implemented for hard constraint '{constraint.id}'.",
        )
    return evaluator(constraint, jd)


def _eval_soft(constraint: SoftConstraint, jd: str) -> SoftConstraintResult:
    cues = _SOFT_CUES.get(constraint.id)
    if cues is None:
        return SoftConstraintResult(
            id=constraint.id,
            label=constraint.label,
            weight=constraint.weight,
            status="skipped",
            reason=f"TODO: no cue list for soft constraint '{constraint.id}'.",
        )
    matched = _find_cues(jd, cues)
    if matched:
        return SoftConstraintResult(
            id=constraint.id,
            label=constraint.label,
            weight=constraint.weight,
            status="matched",
            reason="Preference cues found in JD.",
            matched_cues=matched,
        )
    return SoftConstraintResult(
        id=constraint.id,
        label=constraint.label,
        weight=constraint.weight,
        status="not_matched",
        reason="Preference cues not found in JD (soft – does not block).",
        matched_cues=[],
    )


def evaluate_constraints(
    job_description: str, constraints: Constraints
) -> ConstraintCheckResult:
    jd = _normalize(job_description)
    todos: list[str] = []

    hard_results = [_eval_hard(c, jd) for c in constraints.hard_constraints]
    soft_results = [_eval_soft(c, jd) for c in constraints.soft_constraints]

    # Compensation not evaluable until values are filled (SoT says null).
    if constraints.compensation and (
        constraints.compensation.min_annual_base is None
        and constraints.compensation.target_annual_base is None
    ):
        todos.append(
            "compensation.min_annual_base / target_annual_base are null – "
            "salary gate skipped until filled in constraints.yaml."
        )

    # job_types / location_preferences: informational only until cue rules exist.
    if constraints.job_types:
        todos.append(
            "TODO: job_types preferred/avoid not yet auto-evaluated against JD text."
        )
    if constraints.location_preferences:
        todos.append(
            "TODO: location_preferences beyond remote_first_hybrid_ok hard gate not yet scored."
        )

    failed = [r for r in hard_results if r.status == "failed"]
    unclear = [r for r in hard_results if r.status == "unclear"]
    presence_penalty = [
        r for r in hard_results if r.id == "remote_first_hybrid_ok" and r.status == "penalty"
    ]
    presence_requires_exception = bool(presence_penalty)

    # Work mode must be explicit; unclear remote_first_hybrid_ok → no-go.
    remote_unclear = [r for r in unclear if r.id == "remote_first_hybrid_ok"]
    ownership_unclear = [r for r in unclear if r.id == "product_ownership_required"]
    other_unclear = [
        r
        for r in unclear
        if r.id not in {"remote_first_hybrid_ok", "product_ownership_required"}
    ]
    for item in other_unclear:
        todos.append(
            f"Hard constraint '{item.id}' is unclear – manual review needed "
            f"before apply. Reason: {item.reason}"
        )

    if failed or remote_unclear:
        blockers = failed + remote_unclear
        ids = ", ".join(r.id for r in blockers)
        return ConstraintCheckResult(
            decision="no_go",
            decision_reason=(
                f"Hard constraint gate blocked ({ids}). "
                "Role results left empty."
            ),
            hard_results=hard_results,
            soft_results=soft_results,
            todos=todos,
            verify_product_ownership=False,
            presence_requires_exception=False,
        )

    if presence_requires_exception:
        todos.append(
            "presence_penalty: 2–3 Office-Tage – Ausnahme nur bei außergewöhnlich "
            "starker Rolle (Score ≥ min_score_for_auto_apply); muss in presence_policy "
            "explizit sichtbar sein."
        )

    if ownership_unclear:
        todos.append(
            "verify_product_ownership: Produktverantwortung unklar oder nur implizit – "
            "vor Apply manuell prüfen. Scoring läuft trotzdem."
        )
        return ConstraintCheckResult(
            decision="verify_product_ownership",
            decision_reason=(
                "Produktverantwortung unklar/implizit – "
                "Flag verify_product_ownership gesetzt; Role-Fit-Scoring fortgesetzt."
                + (
                    " Präsenz-Penalty aktiv (2–3 Office-Tage) – Ausnahme nach Scoring."
                    if presence_requires_exception
                    else ""
                )
            ),
            hard_results=hard_results,
            soft_results=soft_results,
            todos=todos,
            verify_product_ownership=True,
            presence_requires_exception=presence_requires_exception,
        )

    reason = "All enabled hard constraints passed; product ownership clear."
    if presence_requires_exception:
        reason = (
            "Hard constraints otherwise clear; Präsenz-Penalty (2–3 Office-Tage) aktiv – "
            "Ausnahmeentscheidung nach Scoring (explizit in presence_policy)."
        )
    elif other_unclear:
        reason = (
            "Hard constraints passed; "
            f"other unclear items flagged as TODO: "
            f"{', '.join(r.id for r in other_unclear)}."
        )

    return ConstraintCheckResult(
        decision="proceed",
        decision_reason=reason,
        hard_results=hard_results,
        soft_results=soft_results,
        todos=todos,
        verify_product_ownership=False,
        presence_requires_exception=presence_requires_exception,
    )
