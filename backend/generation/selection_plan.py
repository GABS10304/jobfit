"""Deterministic CV selection plan (Phase 2) – no LLM, V3 fit-check untouched."""

from __future__ import annotations

import re
from typing import Literal, Optional

from backend.models import (
    CvMaster,
    CvRules,
    Employment,
    FitCheckResponse,
    Project,
    RoleFitProfile,
    RoleFitResult,
    SelectedBullet,
    SelectedEmployment,
    SelectedProject,
    SelectionPlan,
)
from backend.signal_lexicon import SIGNAL_SYNONYMS, candidates_for_signal

_EVIDENCE_RANK: dict[str, int] = {
    "strong": 3,
    "medium": 2,
    "weak": 1,
}

# Prefer outcome/approach wording over raw problem fragments in ATS bullets.
_PROJECT_KIND_BONUS: dict[str, float] = {
    "result": 3.0,
    "approach": 2.0,
    "problem": 0.0,
}
_PROJECT_KIND_TIEBREAK: dict[str, int] = {
    "result": 0,
    "approach": 1,
    "problem": 2,
    "generic": 3,
}

_TOKEN_RE = re.compile(r"[a-z0-9äöüß]{3,}", re.IGNORECASE)


def _normalize(text: str) -> str:
    return text.casefold()


def _evidence_rank(value: Optional[str]) -> int:
    if not value:
        return 0
    return _EVIDENCE_RANK.get(value.casefold().strip(), 0)


def _meets_min_evidence(value: Optional[str], minimum: str) -> bool:
    return _evidence_rank(value) >= _evidence_rank(minimum)


def _has_exclude_marker(text: str, markers: list[str]) -> bool:
    lowered = text.casefold()
    return any(m.casefold() in lowered for m in markers if m)


def _jd_tokens(jd_text: str) -> set[str]:
    return {t.casefold() for t in _TOKEN_RE.findall(jd_text)}


def _keyword_overlap(text: str, jd_tokens: set[str]) -> list[str]:
    """Tokens from CV text that also appear in the JD (mirroring, no invention)."""
    found = sorted({t.casefold() for t in _TOKEN_RE.findall(text)} & jd_tokens)
    return found


def _phrase_in_text(phrase: str, haystack: str) -> bool:
    if not phrase:
        return False
    if len(phrase) <= 3:
        pattern = rf"(?<![a-z0-9äöüß_]){re.escape(phrase)}(?![a-z0-9äöüß_])"
        return re.search(pattern, haystack) is not None
    return phrase in haystack


def _signals_in_jd(signal_ids: list[str], jd_normalized: str) -> list[str]:
    matched: list[str] = []
    for signal in signal_ids:
        for candidate in candidates_for_signal(signal):
            if _phrase_in_text(candidate, jd_normalized):
                matched.append(signal)
                break
    return matched


def _pick_top_role(fit_result: FitCheckResponse) -> RoleFitResult:
    """Prefer top result; fall back to best excluded role (already ranked)."""
    if fit_result.results:
        return fit_result.results[0]
    if fit_result.excluded_roles:
        return fit_result.excluded_roles[0]
    raise ValueError(
        "selection_plan requires at least one role in results or excluded_roles"
    )


def _role_source(fit_result: FitCheckResponse) -> Literal["results", "excluded_roles"]:
    if fit_result.results:
        return "results"
    return "excluded_roles"


def _employment_bullet_candidates(emp: Employment) -> list[tuple[str, Optional[str]]]:
    """(text, inherited evidence_strength) from core_tasks + outcomes."""
    strength = emp.evidence_strength
    items: list[tuple[str, Optional[str]]] = []
    for t in emp.core_tasks:
        items.append((t, strength))
    for t in emp.outcomes:
        items.append((t, strength))
    return items


def _project_bullet_candidates(
    proj: Project,
) -> list[tuple[str, Optional[str], str]]:
    """(text, evidence_strength, kind) – approach/result before problem."""
    strength = proj.evidence_strength
    parts = [
        (proj.approach, "approach"),
        (proj.result, "result"),
        (proj.problem, "problem"),
    ]
    return [(text, strength, kind) for text, kind in parts if text]


def _score_bullet(
    text: str,
    evidence_strength: Optional[str],
    jd_tokens: set[str],
    rules: CvRules,
    kind: str = "generic",
) -> tuple[float, list[str], str] | None:
    if _has_exclude_marker(text, rules.evidence.exclude_markers):
        return None
    if not _meets_min_evidence(
        evidence_strength, rules.evidence.min_strength_for_inclusion
    ):
        return None
    overlap = _keyword_overlap(text, jd_tokens)
    score = (
        float(_evidence_rank(evidence_strength)) * 10.0
        + float(len(overlap))
        + _PROJECT_KIND_BONUS.get(kind, 0.0)
    )
    rationale = (
        f"evidence={evidence_strength or 'unknown'}; "
        f"jd_overlap={len(overlap)}; kind={kind}"
    )
    return score, overlap, rationale


def _select_bullets(
    candidates: list[tuple[str, Optional[str]]]
    | list[tuple[str, Optional[str], str]],
    source_type: Literal["employment", "project"],
    source_id: str,
    jd_tokens: set[str],
    rules: CvRules,
    max_bullets: int,
) -> list[SelectedBullet]:
    scored: list[tuple[SelectedBullet, str]] = []
    for item in candidates:
        if len(item) == 3:
            text, strength, kind = item
        else:
            text, strength = item
            kind = "generic"
        result = _score_bullet(text, strength, jd_tokens, rules, kind)
        if result is None:
            continue
        score, overlap, rationale = result
        scored.append(
            (
                SelectedBullet(
                    source_type=source_type,
                    source_id=source_id,
                    bullet_text=text,
                    evidence_strength=strength,
                    jd_keyword_overlap=overlap,
                    rank_score=score,
                    rationale=rationale,
                ),
                kind,
            )
        )
    scored.sort(
        key=lambda row: (
            -row[0].rank_score,
            _PROJECT_KIND_TIEBREAK.get(row[1], 3),
            row[0].bullet_text,
        )
    )
    return [bullet for bullet, _kind in scored[:max_bullets]]


def _rank_projects(
    projects: list[Project],
    role_id: str,
    role_signals: list[str],
    jd_normalized: str,
) -> list[tuple[Project, float, list[str], str]]:
    ranked: list[tuple[Project, float, list[str], str]] = []
    for proj in projects:
        supports = 1.0 if role_id in proj.supports_roles else 0.0
        jd_hits = _signals_in_jd(role_signals, jd_normalized)
        # Prefer signals that also appear in project text (supports_roles context).
        proj_text = _normalize(
            " ".join(
                filter(
                    None,
                    [
                        proj.title,
                        proj.context,
                        proj.role,
                        proj.problem,
                        proj.approach,
                        proj.result,
                        " ".join(proj.supports_roles),
                    ],
                )
            )
        )
        project_signal_hits = [
            s for s in jd_hits if any(
                _phrase_in_text(c, proj_text) for c in candidates_for_signal(s)
            )
        ]
        # Also count supports_roles overlap with role_id-related JD signals via lexicon on JD.
        signal_overlap = list(dict.fromkeys(project_signal_hits))
        score = (
            supports * 100.0
            + float(len(signal_overlap)) * 10.0
            + float(_evidence_rank(proj.evidence_strength))
        )
        rationale = (
            f"supports_role={supports == 1.0}; "
            f"signal_overlap={len(signal_overlap)}; "
            f"evidence={proj.evidence_strength or 'unknown'}"
        )
        ranked.append((proj, score, signal_overlap, rationale))
    ranked.sort(key=lambda row: (-row[1], row[0].id))
    return ranked


def _rank_employments(
    employments: list[Employment],
    jd_tokens: set[str],
    rules: CvRules,
) -> list[tuple[Employment, float, str]]:
    ranked: list[tuple[Employment, float, str]] = []
    for emp in employments:
        if not _meets_min_evidence(
            emp.evidence_strength, rules.evidence.min_strength_for_inclusion
        ):
            continue
        # Prefer current + strong evidence; boost if tools/tasks overlap JD tokens.
        blob = " ".join(
            emp.core_tasks + emp.outcomes + emp.tools_methods + [emp.role_title, emp.company]
        )
        overlap = _keyword_overlap(blob, jd_tokens)
        score = (
            float(_evidence_rank(emp.evidence_strength)) * 20.0
            + (10.0 if emp.current else 0.0)
            + float(len(overlap))
        )
        rationale = (
            f"evidence={emp.evidence_strength or 'unknown'}; "
            f"current={emp.current}; jd_overlap={len(overlap)}"
        )
        ranked.append((emp, score, rationale))
    ranked.sort(key=lambda row: (-row[1], row[0].id))
    return ranked


def selection_plan(
    cv_master: CvMaster,
    role_fit_profile: RoleFitProfile,
    fit_result: FitCheckResponse,
    jd_text: str,
    cv_rules: CvRules,
) -> SelectionPlan:
    """Build an explainable, deterministic SelectionPlan from fit output + CV master."""
    top = _pick_top_role(fit_result)
    source = _role_source(fit_result)
    role_meta = next(
        (r for r in role_fit_profile.roles if r.role_id == top.role_id),
        None,
    )
    role_signals = list(
        dict.fromkeys(
            (role_meta.core_signals_skills if role_meta else [])
            + (role_meta.core_signals_domains if role_meta else [])
            + (role_meta.core_signals_tools if role_meta else [])
            + (role_meta.optional_signals_tools if role_meta else [])
            + top.matched_signals
        )
    )

    jd_normalized = _normalize(jd_text)
    jd_tokens = _jd_tokens(jd_text)
    # Keep lexicon-backed phrases available for token overlap enrichment.
    for signal in role_signals:
        for phrase in SIGNAL_SYNONYMS.get(signal, ()):
            for tok in _TOKEN_RE.findall(phrase):
                jd_tokens.add(tok.casefold())
        for tok in _TOKEN_RE.findall(signal.replace("_", " ")):
            jd_tokens.add(tok.casefold())

    emp_ranked = _rank_employments(
        cv_master.employments, jd_tokens, cv_rules
    )[: cv_rules.limits.max_employments]

    selected_emps: list[SelectedEmployment] = []
    for emp, _score, emp_rationale in emp_ranked:
        bullets = _select_bullets(
            _employment_bullet_candidates(emp),
            "employment",
            emp.id,
            jd_tokens,
            cv_rules,
            cv_rules.limits.max_bullets_per_employment,
        )
        selected_emps.append(
            SelectedEmployment(
                employment_id=emp.id,
                bullets=bullets,
                rationale=emp_rationale,
            )
        )

    proj_ranked = _rank_projects(
        cv_master.projects, top.role_id, role_signals, jd_normalized
    )[: cv_rules.limits.max_projects]

    selected_projs: list[SelectedProject] = []
    for proj, pscore, matched, proj_rationale in proj_ranked:
        bullets = _select_bullets(
            _project_bullet_candidates(proj),
            "project",
            proj.id,
            jd_tokens,
            cv_rules,
            cv_rules.limits.max_bullets_per_project,
        )
        selected_projs.append(
            SelectedProject(
                project_id=proj.id,
                rank_score=pscore,
                matched_signals=matched,
                bullets=bullets,
                rationale=proj_rationale,
            )
        )

    rationale = (
        f"Rolle {top.role_id} aus {source} (score={top.score}). "
        f"{len(selected_emps)} Employments, {len(selected_projs)} Projects "
        f"nach evidence/limits und JD-Overlap."
    )
    explain = {
        "role_pick": f"{top.role_id} via {source}",
        "evidence_gate": (
            f"min_strength={cv_rules.evidence.min_strength_for_inclusion}; "
            f"exclude_markers={cv_rules.evidence.exclude_markers}"
        ),
        "limits": (
            f"max_employments={cv_rules.limits.max_employments}, "
            f"max_projects={cv_rules.limits.max_projects}, "
            f"max_bullets_emp={cv_rules.limits.max_bullets_per_employment}, "
            f"max_bullets_proj={cv_rules.limits.max_bullets_per_project}, "
            f"max_certifications={cv_rules.limits.max_certifications}"
        ),
        "keyword_mirroring": cv_rules.keyword_mirroring.note
        or "cv_master_only / no_invention",
        "language": cv_rules.language.default,
    }

    return SelectionPlan(
        selected_role_id=top.role_id,
        selected_role_name=top.role_name,
        role_source=source,
        role_score=top.score,
        matched_signals=list(top.matched_signals),
        selected_employment_ids=[e.employment_id for e in selected_emps],
        selected_project_ids=[p.project_id for p in selected_projs],
        employments=selected_emps,
        projects=selected_projs,
        rationale=rationale,
        explain=explain,
    )
