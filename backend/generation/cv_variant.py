"""Render an ATS-friendly German CV text from a SelectionPlan (Phase 2).

Deterministic only: no LLM, no invented achievements. V3 fit-check untouched.
"""

from __future__ import annotations

import re

from backend.models import (
    CvMaster,
    CvRules,
    Employment,
    Project,
    SelectionPlan,
)

# German section headers for ATS-friendly single-column markdown.
_SECTION_HEADERS: dict[str, str] = {
    "profile": "Profil",
    "employments": "Berufserfahrung",
    "projects": "Projekte",
    "skills": "Kompetenzen",
    "tools": "Tools",
    "certifications": "Zertifizierungen",
}

# Master-CV provenance tags are SSOT annotations, not ATS content.
_EVIDENCE_TAG_RE = re.compile(
    r"\s*\[(?:TODO|(?:teilweise\s+|qualitativ\s+)?belegt(?:\s+durch\s+[^\]]+)?)\]",
    re.IGNORECASE,
)


def _ats_bullet_text(text: str) -> str:
    """Strip internal evidence/provenance tags; keep claim text unchanged."""
    cleaned = _EVIDENCE_TAG_RE.sub("", text).strip()
    return re.sub(r"\s{2,}", " ", cleaned)


def _date_range(emp: Employment) -> str:
    end = "heute" if emp.current else (emp.end or "")
    if end:
        return f"{emp.start} – {end}"
    return emp.start


def _profile_line(plan: SelectionPlan, cv_master: CvMaster) -> str:
    """Short role-based profile line – no invented achievements."""
    kernel = (cv_master.person.profile_kernel or "").strip()
    if kernel:
        kernel = kernel[0].upper() + kernel[1:]
    role = plan.selected_role_name or plan.selected_role_id
    if kernel:
        return f"Ausrichtung: {role}. {kernel}"
    return f"Ausrichtung: {role}."


def _section_title(key: str, *, plain: bool) -> str:
    label = _SECTION_HEADERS[key]
    return f"{label}:" if plain else f"## {label}"


def _render_header(cv_master: CvMaster, *, plain: bool = False) -> list[str]:
    person = cv_master.person
    lines = [person.name if plain else f"# {person.name}", ""]
    meta: list[str] = []
    if person.location:
        meta.append(person.location)
    if person.languages:
        meta.append(" · ".join(person.languages))
    if meta:
        lines.append(" | ".join(meta))
        lines.append("")
    return lines


def _render_profile(
    plan: SelectionPlan, cv_master: CvMaster, *, plain: bool = False
) -> list[str]:
    return [
        _section_title("profile", plain=plain),
        "",
        _profile_line(plan, cv_master),
        "",
    ]


def _emp_by_id(cv_master: CvMaster) -> dict[str, Employment]:
    return {e.id: e for e in cv_master.employments}


def _proj_by_id(cv_master: CvMaster) -> dict[str, Project]:
    return {p.id: p for p in cv_master.projects}


def _render_employments(
    plan: SelectionPlan, cv_master: CvMaster, *, plain: bool = False
) -> list[str]:
    lines = [_section_title("employments", plain=plain), ""]
    lookup = _emp_by_id(cv_master)
    for selected in plan.employments:
        emp = lookup.get(selected.employment_id)
        if emp is None:
            continue
        loc = f" | {emp.location}" if emp.location else ""
        role_line = f"{emp.role_title} – {emp.company}"
        lines.append(role_line if plain else f"### {role_line}")
        lines.append(f"{_date_range(emp)}{loc}")
        lines.append("")
        for bullet in selected.bullets:
            text = _ats_bullet_text(bullet.bullet_text)
            if text:
                lines.append(f"- {text}")
        lines.append("")
    return lines


def _render_projects(
    plan: SelectionPlan, cv_master: CvMaster, *, plain: bool = False
) -> list[str]:
    lines = [_section_title("projects", plain=plain), ""]
    lookup = _proj_by_id(cv_master)
    for selected in plan.projects:
        proj = lookup.get(selected.project_id)
        if proj is None:
            continue
        context = f" ({proj.context})" if proj.context else ""
        title_line = f"{proj.title}{context}"
        lines.append(title_line if plain else f"### {title_line}")
        if proj.role:
            lines.append(f"Rolle: {proj.role}")
        if proj.repo_url:
            lines.append(f"Repo: {proj.repo_url}")
        lines.append("")
        for bullet in selected.bullets:
            text = _ats_bullet_text(bullet.bullet_text)
            if text:
                lines.append(f"- {text}")
        lines.append("")
    return lines


def _render_skills(cv_master: CvMaster, *, plain: bool = False) -> list[str]:
    """Skills from master; include medium+ strength only when set."""
    lines = [_section_title("skills", plain=plain), ""]
    if not cv_master.skills:
        return lines
    names: list[str] = []
    for skill in cv_master.skills:
        strength = (skill.strength or "medium").casefold()
        if strength in {"strong", "medium"}:
            names.append(skill.name)
    if not names:
        names = [s.name for s in cv_master.skills]
    lines.append(", ".join(names))
    lines.append("")
    return lines


def _render_tools(cv_master: CvMaster, *, plain: bool = False) -> list[str]:
    lines = [_section_title("tools", plain=plain), ""]
    if cv_master.tools:
        lines.append(", ".join(cv_master.tools))
        lines.append("")
    return lines


def _render_certifications(
    cv_master: CvMaster, cv_rules: CvRules, *, plain: bool = False
) -> list[str]:
    lines = [_section_title("certifications", plain=plain), ""]
    limit = cv_rules.limits.max_certifications
    certs = cv_master.certifications[:limit] if limit > 0 else []
    for cert in certs:
        lines.append(f"- {cert}")
    if certs:
        lines.append("")
    return lines


def _generate_cv_variant(
    selection_plan: SelectionPlan,
    cv_master: CvMaster,
    cv_rules: CvRules,
    *,
    plain: bool,
) -> str:
    parts: list[str] = _render_header(cv_master, plain=plain)

    order = cv_rules.section_order or list(_SECTION_HEADERS.keys())
    for section in order:
        if section == "profile":
            parts.extend(_render_profile(selection_plan, cv_master, plain=plain))
        elif section == "employments":
            parts.extend(
                _render_employments(selection_plan, cv_master, plain=plain)
            )
        elif section == "projects":
            parts.extend(_render_projects(selection_plan, cv_master, plain=plain))
        elif section == "skills":
            parts.extend(_render_skills(cv_master, plain=plain))
        elif section == "tools":
            parts.extend(_render_tools(cv_master, plain=plain))
        elif section == "certifications":
            parts.extend(
                _render_certifications(cv_master, cv_rules, plain=plain)
            )
        else:
            # Unknown section key in cv_rules – skip, do not invent content.
            continue

    return "\n".join(parts).rstrip() + "\n"


def generate_cv_variant(
    selection_plan: SelectionPlan,
    cv_master: CvMaster,
    cv_rules: CvRules,
) -> str:
    """Render single-column ATS-friendly German CV markdown from SelectionPlan.

    Uses only selected employments/projects/bullets. Profile is a short
    role-based line (no invented achievements). Section order from cv_rules.
    """
    return _generate_cv_variant(
        selection_plan, cv_master, cv_rules, plain=False
    )


def generate_cv_variant_plain(
    selection_plan: SelectionPlan,
    cv_master: CvMaster,
    cv_rules: CvRules,
) -> str:
    """Render ATS plain-text CV (simple labels, no markdown headings).

    Better for paste into ATS forms that strip or mishandle markdown.
    Same content selection as ``generate_cv_variant``.
    """
    return _generate_cv_variant(
        selection_plan, cv_master, cv_rules, plain=True
    )
