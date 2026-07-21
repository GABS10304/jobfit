"""Render an ATS-friendly German CV text from a SelectionPlan (Phase 2).

Deterministic only: no LLM, no invented achievements. V3 fit-check untouched.
"""

from __future__ import annotations

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


def _date_range(emp: Employment) -> str:
    end = "heute" if emp.current else (emp.end or "")
    if end:
        return f"{emp.start} – {end}"
    return emp.start


def _profile_line(plan: SelectionPlan, cv_master: CvMaster) -> str:
    """Short role-based profile line – no invented achievements."""
    kernel = (cv_master.person.profile_kernel or "").strip()
    role = plan.selected_role_name or plan.selected_role_id
    if kernel:
        return f"Ausrichtung: {role}. {kernel}"
    return f"Ausrichtung: {role}."


def _render_header(cv_master: CvMaster) -> list[str]:
    person = cv_master.person
    lines = [f"# {person.name}", ""]
    meta: list[str] = []
    if person.location:
        meta.append(person.location)
    if person.languages:
        meta.append(" · ".join(person.languages))
    if meta:
        lines.append(" | ".join(meta))
        lines.append("")
    return lines


def _render_profile(plan: SelectionPlan, cv_master: CvMaster) -> list[str]:
    return [
        f"## {_SECTION_HEADERS['profile']}",
        "",
        _profile_line(plan, cv_master),
        "",
    ]


def _emp_by_id(cv_master: CvMaster) -> dict[str, Employment]:
    return {e.id: e for e in cv_master.employments}


def _proj_by_id(cv_master: CvMaster) -> dict[str, Project]:
    return {p.id: p for p in cv_master.projects}


def _render_employments(plan: SelectionPlan, cv_master: CvMaster) -> list[str]:
    lines = [f"## {_SECTION_HEADERS['employments']}", ""]
    lookup = _emp_by_id(cv_master)
    for selected in plan.employments:
        emp = lookup.get(selected.employment_id)
        if emp is None:
            continue
        loc = f" | {emp.location}" if emp.location else ""
        lines.append(f"### {emp.role_title} – {emp.company}")
        lines.append(f"{_date_range(emp)}{loc}")
        lines.append("")
        for bullet in selected.bullets:
            lines.append(f"- {bullet.bullet_text}")
        lines.append("")
    return lines


def _render_projects(plan: SelectionPlan, cv_master: CvMaster) -> list[str]:
    lines = [f"## {_SECTION_HEADERS['projects']}", ""]
    lookup = _proj_by_id(cv_master)
    for selected in plan.projects:
        proj = lookup.get(selected.project_id)
        if proj is None:
            continue
        context = f" ({proj.context})" if proj.context else ""
        lines.append(f"### {proj.title}{context}")
        if proj.role:
            lines.append(f"Rolle: {proj.role}")
        lines.append("")
        for bullet in selected.bullets:
            lines.append(f"- {bullet.bullet_text}")
        lines.append("")
    return lines


def _render_skills(cv_master: CvMaster) -> list[str]:
    """Skills from master; include medium+ strength only when set."""
    lines = [f"## {_SECTION_HEADERS['skills']}", ""]
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


def _render_tools(cv_master: CvMaster) -> list[str]:
    lines = [f"## {_SECTION_HEADERS['tools']}", ""]
    if cv_master.tools:
        lines.append(", ".join(cv_master.tools))
        lines.append("")
    return lines


def _render_certifications(cv_master: CvMaster) -> list[str]:
    lines = [f"## {_SECTION_HEADERS['certifications']}", ""]
    for cert in cv_master.certifications:
        lines.append(f"- {cert}")
    if cv_master.certifications:
        lines.append("")
    return lines


def generate_cv_variant(
    selection_plan: SelectionPlan,
    cv_master: CvMaster,
    cv_rules: CvRules,
) -> str:
    """Render single-column ATS-friendly German CV markdown from SelectionPlan.

    Uses only selected employments/projects/bullets. Profile is a short
    role-based line (no invented achievements). Section order from cv_rules.
    """
    parts: list[str] = _render_header(cv_master)

    order = cv_rules.section_order or list(_SECTION_HEADERS.keys())
    for section in order:
        if section == "profile":
            parts.extend(_render_profile(selection_plan, cv_master))
        elif section == "employments":
            parts.extend(_render_employments(selection_plan, cv_master))
        elif section == "projects":
            parts.extend(_render_projects(selection_plan, cv_master))
        elif section == "skills":
            parts.extend(_render_skills(cv_master))
        elif section == "tools":
            parts.extend(_render_tools(cv_master))
        elif section == "certifications":
            parts.extend(_render_certifications(cv_master))
        else:
            # Unknown section key in cv_rules – skip, do not invent content.
            continue

    text = "\n".join(parts).rstrip() + "\n"
    return text
