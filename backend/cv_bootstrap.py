"""Deterministic CV bootstrap → draft profile + Master-CV-style markdown.

No LLM. Uses signal_lexicon + role_fit_profile catalog. Hard constraints are
intentionally not inferred from CV text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend import data_loader
from backend.fit_engine import role_rank_tier
from backend.models import (
    Constraints,
    CvMaster,
    Person,
    RoleFitProfile,
    RoleSignals,
    Skill,
    UserProfile,
)
from backend.signal_lexicon import SIGNAL_SYNONYMS, candidates_for_signal

# Title hints → catalog role_id (first match wins by score accumulation).
_ROLE_TITLE_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "ai_product_manager",
        (
            "ai product manager",
            "ki product manager",
            "ki-product manager",
            "agentic ai",
            "ai pm",
        ),
    ),
    (
        "technical_product_manager",
        ("technical product manager", "technischer product manager", "tpm"),
    ),
    (
        "b2b_saas_govtech_product_lead",
        ("product lead", "head of product"),
    ),
    (
        "product_transformation_lead",
        ("product transformation", "transformations lead"),
    ),
    (
        "agile_transformation_consultant",
        (
            "agile transformation",
            "transformation consultant",
            "transformation coach",
        ),
    ),
    ("agile_coach", ("agile coach", "team coach")),
    ("scrum_master", ("scrum master", "scrummaster")),
    ("agile_project_lead", ("agile project", "project lead", "projektleiter")),
    ("client_solutions_lead", ("solutions lead", "client solutions", "functional consultant")),
    ("product_operations", ("product operations", "product ops")),
)


@dataclass
class BootstrapResult:
    profile: UserProfile
    cv_draft_md: str
    matched_signal_ids: list[str] = field(default_factory=list)
    suggested_role_id: str | None = None
    notes: list[str] = field(default_factory=list)


def _normalize(text: str) -> str:
    return text.casefold()


def _phrase_in_text(phrase: str, haystack: str) -> bool:
    if not phrase:
        return False
    if len(phrase) <= 3:
        pattern = rf"(?<![a-z0-9äöüß_]){re.escape(phrase)}(?![a-z0-9äöüß_])"
        return re.search(pattern, haystack) is not None
    return phrase in haystack


def detect_signals_in_text(text: str) -> list[str]:
    """Return signal ids whose lexicon candidates appear in text."""
    hay = _normalize(text)
    found: list[str] = []
    for signal_id in SIGNAL_SYNONYMS:
        for cand in candidates_for_signal(signal_id):
            if _phrase_in_text(cand, hay):
                found.append(signal_id)
                break
    # also bare token ids that may not be in synonym map keys only — keys cover lexicon
    return sorted(set(found))


def _catalog_buckets(catalog: RoleFitProfile) -> tuple[set[str], set[str], set[str]]:
    skills: set[str] = set()
    domains: set[str] = set()
    tools: set[str] = set()
    for role in catalog.roles:
        skills.update(role.core_signals_skills)
        domains.update(role.core_signals_domains)
        tools.update(role.core_signals_tools)
        tools.update(role.optional_signals_tools)
    return skills, domains, tools


def _guess_name(text: str, filename: str | None) -> str:
    for line in text.splitlines():
        clean = line.strip().lstrip("#").strip()
        if not clean or len(clean) > 60:
            continue
        if clean.lower().startswith(("curriculum", "lebenslauf", "resume", "cv ")):
            continue
        if re.search(r"\d{4}", clean):
            continue
        if "@" in clean or "http" in clean.lower():
            continue
        # Prefer lines that look like a person name (2–4 words, letters)
        if re.fullmatch(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\-']+(?: [A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\-']+){0,3}", clean):
            return clean
    if filename:
        stem = re.sub(r"(?i)\.(pdf|docx|md|txt|markdown)$", "", filename)
        stem = re.sub(r"[_\-]+", " ", stem).strip()
        if stem and len(stem) < 60:
            return stem.title()
    return "Unbekannt"


def _score_roles(
    text: str,
    matched: set[str],
    catalog: RoleFitProfile,
) -> list[tuple[str, int]]:
    hay = _normalize(text)
    scores: dict[str, int] = {r.role_id: 0 for r in catalog.roles}
    for role_id, hints in _ROLE_TITLE_HINTS:
        if role_id not in scores:
            continue
        best_title = 0
        for hint in hints:
            if _phrase_in_text(hint, hay):
                # One best title hit per role (avoid stacking synonyms on long CVs).
                best_title = max(best_title, 40 + min(30, len(hint)))
        scores[role_id] += best_title
    for role in catalog.roles:
        role_sigs = set(role.core_signals_skills) | set(role.core_signals_domains)
        role_sigs |= set(role.core_signals_tools) | set(role.optional_signals_tools)
        overlap = len(matched & role_sigs)
        scores[role.role_id] += overlap
    ranked = sorted(
        scores.items(),
        key=lambda kv: (-kv[1], role_rank_tier(kv[0]), kv[0]),
    )
    return ranked


def _build_role_signals(
    catalog_role: RoleSignals,
    matched: set[str],
    all_skills: set[str],
    all_domains: set[str],
    all_tools: set[str],
) -> RoleSignals:
    skills = [s for s in catalog_role.core_signals_skills if s in matched]
    domains = [s for s in catalog_role.core_signals_domains if s in matched]
    tools = [
        s
        for s in (catalog_role.core_signals_tools + catalog_role.optional_signals_tools)
        if s in matched
    ]
    # Keep extra matched skills/domains not on this role but known in catalog
    for sid in sorted(matched):
        if sid in all_skills and sid not in skills:
            skills.append(sid)
        elif sid in all_domains and sid not in domains:
            domains.append(sid)
        elif sid in all_tools and sid not in tools:
            tools.append(sid)
    return RoleSignals(
        role_id=catalog_role.role_id,
        role_name=catalog_role.role_name,
        core_signals_skills=skills,
        core_signals_domains=domains,
        core_signals_tools=tools,
    )


def render_cv_draft_md(
    *,
    name: str,
    matched_skills: list[str],
    matched_domains: list[str],
    matched_tools: list[str],
    role_id: str | None,
    role_name: str | None,
    source_filename: str | None,
    notes: list[str],
) -> str:
    """Markdown shaped like domain/Master-CV-structured.md (lightweight)."""
    lines = [
        "# Master CV – Draft (aus Upload)",
        "",
        "## Person",
        f"- **Name:** {name}",
        "- **Standort:**",
        "- **Sprachen:**",
        "- **Profilkern:**",
        "",
        "## Vorgeschlagene Zielrolle",
        f"- **role_id:** {role_id or '—'}",
        f"- **role_name:** {role_name or '—'}",
        "",
        "## Erkannte Signale",
        "",
        "### Skills",
    ]
    if matched_skills:
        lines.extend(f"- {s}" for s in matched_skills)
    else:
        lines.append("- (keine)")
    lines.extend(["", "### Domains"])
    if matched_domains:
        lines.extend(f"- {s}" for s in matched_domains)
    else:
        lines.append("- (keine)")
    lines.extend(["", "### Tools"])
    if matched_tools:
        lines.extend(f"- {s}" for s in matched_tools)
    else:
        lines.append("- (keine)")
    lines.extend(
        [
            "",
            "## Stationen",
            "- (noch nicht strukturiert – bitte in der Maske / später nachziehen)",
            "",
            "## Quelle",
            f"- Datei: {source_filename or 'upload'}",
            "- Indikator-Referenz: `domain/Master-CV-structured.md`",
            "",
            "## Hinweise",
        ]
    )
    if notes:
        lines.extend(f"- {n}" for n in notes)
    else:
        lines.append("- —")
    lines.append("")
    return "\n".join(lines)


def bootstrap_from_text(
    text: str,
    *,
    user_id: str,
    display_name: str = "",
    source_filename: str | None = None,
) -> BootstrapResult:
    catalog = data_loader.load_role_fit_profile()
    all_skills, all_domains, all_tools = _catalog_buckets(catalog)
    matched = set(detect_signals_in_text(text))
    ranked = _score_roles(text, matched, catalog)
    notes = [
        "Hard Constraints (Remote / Sales / Ownership) werden nicht aus dem CV geraten.",
        "Bitte in der Maske bestätigen und fehlende Pflichtfelder ergänzen.",
    ]
    if not matched:
        notes.append("Keine Lexikon-Signale erkannt – Skills manuell eintragen.")

    top_id, top_score = ranked[0] if ranked else (None, 0)
    catalog_role = next((r for r in catalog.roles if r.role_id == top_id), None)
    if catalog_role is None or top_score <= 0:
        # Fallback: first catalog role with empty signals if nothing scored
        if catalog.roles and matched:
            catalog_role = catalog.roles[0]
            top_id = catalog_role.role_id
            notes.append("Rollenwahl unsicher – erste Katalogrolle als Vorschlag.")
        elif catalog.roles:
            catalog_role = catalog.roles[0]
            top_id = catalog_role.role_id
            notes.append("Schwache Rollen-Hinweise – Vorschlag prüfen.")

    assert catalog_role is not None
    role = _build_role_signals(
        catalog_role, matched, all_skills, all_domains, all_tools
    )

    name = display_name.strip() or _guess_name(text, source_filename)
    skills_list = list(role.core_signals_skills)
    domains_list = list(role.core_signals_domains)
    tools_list = list(role.core_signals_tools)

    cv_master = CvMaster(
        person=Person(name=name, profile_kernel=None),
        skills=[Skill(id=s, name=s.replace("_", " ")) for s in skills_list],
        tools=[t.replace("_", " ") for t in tools_list],
    )

    draft_md = render_cv_draft_md(
        name=name,
        matched_skills=skills_list,
        matched_domains=domains_list,
        matched_tools=tools_list,
        role_id=role.role_id,
        role_name=role.role_name,
        source_filename=source_filename,
        notes=notes,
    )

    profile = UserProfile(
        user_id=user_id,
        display_name=name,
        profile_version="0.1-cv-bootstrap",
        role_fit_profile=RoleFitProfile(version="0.1", roles=[role]),
        # Hard constraints intentionally empty → Completeness zeigt Lücken
        constraints=Constraints(),
        cv_master=cv_master,
    )

    return BootstrapResult(
        profile=profile,
        cv_draft_md=draft_md,
        matched_signal_ids=sorted(matched),
        suggested_role_id=role.role_id,
        notes=notes,
    )
