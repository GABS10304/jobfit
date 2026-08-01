"""Styled HTML -> PDF CV rendering via Playwright (Chromium print-to-PDF).

Same source data as cv_variant.py (SelectionPlan + CvMaster + CvRules) —
this is a second renderer, not a parser of the markdown output, so there is
no lossy round-trip. Still single-column with real, selectable text (no
multi-column layout), so it stays ATS-safe like the fpdf2 renderer in
cv_pdf.py; only the typography/spacing/color improves, and — for the German
variant only — an optional profile photo (outside the text reading order,
so it doesn't affect ATS text extraction; see backend/generation/ats_check.py).
English-market CVs conventionally omit a photo, so it's gated on `language`.
"""

from __future__ import annotations

import base64
from html import escape
from pathlib import Path

from backend.generation.cv_variant import _ats_bullet_text, _date_range
from backend.models import CvMaster, CvRules, Employment, Project, SelectionPlan

_FONT_PATH = Path(__file__).resolve().parent / "fonts" / "DejaVuSans.ttf"
_PHOTO_PATH = Path(__file__).resolve().parent.parent.parent / "domain" / "assets" / "profile_photo.jpg"

_SECTION_TITLES: dict[str, str] = {
    "profile": "Profil",
    "employments": "Berufserfahrung",
    "projects": "Projekte",
    "skills": "Kompetenzen",
    "tools": "Tools",
    "certifications": "Zertifizierungen",
}

_CSS_TEMPLATE = """
@font-face {{
  font-family: 'CVFont';
  src: url(data:font/truetype;base64,{font_b64}) format('truetype');
  font-weight: 400 700;
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}
body {{
  font-family: 'CVFont', sans-serif;
  font-size: 10pt;
  line-height: 1.38;
  color: #1a1a1a;
  padding: 15mm 16mm;
}}
header.cv-header {{ margin-bottom: 3.5mm; }}
header.cv-header .header-flex {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 6mm;
}}
header.cv-header h1 {{
  margin: 0 0 1.3mm 0;
  font-size: 20pt;
  font-weight: 700;
  color: #1f3a5f;
  letter-spacing: 0.2px;
}}
header.cv-header .meta {{ font-size: 9.1pt; color: #5b6472; }}
header.cv-header .photo {{
  width: 26mm;
  height: 26mm;
  object-fit: cover;
  border-radius: 2mm;
  flex: none;
}}
header.cv-header hr.rule {{
  margin-top: 2.6mm;
  border: none;
  border-top: 1.6px solid #1f3a5f;
}}
section.cv-section {{ margin-top: 4mm; break-inside: avoid-page; }}
section.cv-section:first-of-type {{ margin-top: 0; }}
section.cv-section h2 {{
  font-size: 9.6pt;
  font-weight: 700;
  letter-spacing: 1.1px;
  text-transform: uppercase;
  color: #1f3a5f;
  margin: 0 0 1.8mm 0;
  padding-bottom: 0.9mm;
  border-bottom: 0.75px solid #d7dbe0;
}}
.entry {{ margin-bottom: 2.8mm; break-inside: avoid-page; }}
.entry:last-child {{ margin-bottom: 0; }}
.entry-title {{ font-size: 10pt; font-weight: 700; }}
.entry-meta {{ font-size: 8.8pt; color: #5b6472; margin-top: 0.2mm; }}
.entry ul {{ margin: 1.3mm 0 0 0; padding-left: 4.2mm; }}
.entry li {{ margin-bottom: 0.6mm; }}
p.cv-paragraph {{ margin: 0; }}
p.cv-inline-list {{ margin: 0; }}
ul.cv-plain-list {{ margin: 0; padding-left: 4.2mm; }}
ul.cv-plain-list li {{ margin-bottom: 0.6mm; break-inside: avoid-page; }}
"""


def _font_base64() -> str:
    if not _FONT_PATH.is_file():
        raise FileNotFoundError(
            f"Bundled CV font missing: {_FONT_PATH}. Expected DejaVuSans.ttf next to cv_pdf.py."
        )
    return base64.b64encode(_FONT_PATH.read_bytes()).decode("ascii")


def _photo_base64() -> str | None:
    """Base64 JPEG data, or None if no local photo asset is present.

    domain/assets/ is gitignored (biometric photo, kept local-only) — a
    fresh clone simply renders without a photo rather than erroring.
    """
    if not _PHOTO_PATH.is_file():
        return None
    return base64.b64encode(_PHOTO_PATH.read_bytes()).decode("ascii")


def _render_header_html(cv_master: CvMaster, *, language: str = "de") -> str:
    person = cv_master.person
    meta_parts: list[str] = []
    if person.location:
        meta_parts.append(escape(person.location))
    if person.languages:
        meta_parts.append(escape(" · ".join(person.languages)))
    meta_html = f'<div class="meta">{" | ".join(meta_parts)}</div>' if meta_parts else ""

    name_block = f"<h1>{escape(person.name)}</h1>{meta_html}"

    photo_html = ""
    if language == "de":
        photo_b64 = _photo_base64()
        if photo_b64:
            photo_html = (
                f'<img class="photo" src="data:image/jpeg;base64,{photo_b64}" '
                f'alt="{escape(person.name)}">'
            )

    return (
        '<header class="cv-header">'
        f'<div class="header-flex"><div>{name_block}</div>{photo_html}</div>'
        '<hr class="rule">'
        "</header>"
    )


def _profile_line(plan: SelectionPlan, cv_master: CvMaster) -> str:
    kernel = (cv_master.person.profile_kernel or "").strip()
    if kernel:
        kernel = kernel[0].upper() + kernel[1:]
    role = plan.selected_role_name or plan.selected_role_id
    if kernel:
        return f"Ausrichtung: {role}. {kernel}"
    return f"Ausrichtung: {role}."


def _section_wrap(key: str, body_html: str) -> str:
    title = _SECTION_TITLES[key]
    return f'<section class="cv-section"><h2>{escape(title)}</h2>{body_html}</section>'


def _render_profile_html(plan: SelectionPlan, cv_master: CvMaster) -> str:
    line = escape(_profile_line(plan, cv_master))
    return _section_wrap("profile", f'<p class="cv-paragraph">{line}</p>')


def _emp_by_id(cv_master: CvMaster) -> dict[str, Employment]:
    return {e.id: e for e in cv_master.employments}


def _proj_by_id(cv_master: CvMaster) -> dict[str, Project]:
    return {p.id: p for p in cv_master.projects}


def _bullets_html(bullets) -> str:
    items = []
    for bullet in bullets:
        text = _ats_bullet_text(bullet.bullet_text)
        if text:
            items.append(f"<li>{escape(text)}</li>")
    return f"<ul>{''.join(items)}</ul>" if items else ""


def _render_employments_html(plan: SelectionPlan, cv_master: CvMaster) -> str:
    lookup = _emp_by_id(cv_master)
    entries: list[str] = []
    for selected in plan.employments:
        emp = lookup.get(selected.employment_id)
        if emp is None:
            continue
        loc = f" | {escape(emp.location)}" if emp.location else ""
        title = f"{escape(emp.role_title)} – {escape(emp.company)}"
        meta = f"{escape(_date_range(emp))}{loc}"
        entries.append(
            '<div class="entry">'
            f'<div class="entry-title">{title}</div>'
            f'<div class="entry-meta">{meta}</div>'
            f"{_bullets_html(selected.bullets)}"
            "</div>"
        )
    return _section_wrap("employments", "".join(entries))


def _render_projects_html(plan: SelectionPlan, cv_master: CvMaster) -> str:
    lookup = _proj_by_id(cv_master)
    entries: list[str] = []
    for selected in plan.projects:
        proj = lookup.get(selected.project_id)
        if proj is None:
            continue
        context = f" ({escape(proj.context)})" if proj.context else ""
        title = f"{escape(proj.title)}{context}"
        meta_lines: list[str] = []
        if proj.role:
            meta_lines.append(f"Rolle: {escape(proj.role)}")
        if proj.repo_url:
            meta_lines.append(f"Repo: {escape(proj.repo_url)}")
        meta_html = (
            f'<div class="entry-meta">{"<br>".join(meta_lines)}</div>' if meta_lines else ""
        )
        entries.append(
            '<div class="entry">'
            f'<div class="entry-title">{title}</div>'
            f"{meta_html}"
            f"{_bullets_html(selected.bullets)}"
            "</div>"
        )
    return _section_wrap("projects", "".join(entries))


def _render_skills_html(cv_master: CvMaster) -> str:
    if not cv_master.skills:
        return _section_wrap("skills", "")
    names = [
        s.name for s in cv_master.skills if (s.strength or "medium").casefold() in {"strong", "medium"}
    ]
    if not names:
        names = [s.name for s in cv_master.skills]
    line = escape(", ".join(names))
    return _section_wrap("skills", f'<p class="cv-inline-list">{line}</p>')


def _render_tools_html(cv_master: CvMaster) -> str:
    if not cv_master.tools:
        return _section_wrap("tools", "")
    line = escape(", ".join(cv_master.tools))
    return _section_wrap("tools", f'<p class="cv-inline-list">{line}</p>')


def _render_certifications_html(cv_master: CvMaster, cv_rules: CvRules) -> str:
    limit = cv_rules.limits.max_certifications
    certs = cv_master.certifications[:limit] if limit > 0 else []
    if not certs:
        return _section_wrap("certifications", "")
    items = "".join(f"<li>{escape(cert)}</li>" for cert in certs)
    return _section_wrap("certifications", f'<ul class="cv-plain-list">{items}</ul>')


def cv_content_html(
    selection_plan: SelectionPlan,
    cv_master: CvMaster,
    cv_rules: CvRules,
    *,
    language: str = "de",
) -> str:
    """Render just the CV's body content (header + sections), no <html> shell.

    Reused as-is by generate_cv_variant_html (standalone CV doc) and by
    application_html.py (combined cover-letter + CV document).

    `language` only gates the photo (German-market convention) right now —
    it does not translate section labels/content; see cv_translate.py for
    the English-content path, which currently targets the plain-text/fpdf2
    renderer, not this one.
    """
    body_parts = [_render_header_html(cv_master, language=language)]

    order = cv_rules.section_order or list(_SECTION_TITLES.keys())
    for section in order:
        if section == "profile":
            body_parts.append(_render_profile_html(selection_plan, cv_master))
        elif section == "employments":
            body_parts.append(_render_employments_html(selection_plan, cv_master))
        elif section == "projects":
            body_parts.append(_render_projects_html(selection_plan, cv_master))
        elif section == "skills":
            body_parts.append(_render_skills_html(cv_master))
        elif section == "tools":
            body_parts.append(_render_tools_html(cv_master))
        elif section == "certifications":
            body_parts.append(_render_certifications_html(cv_master, cv_rules))
        # Unknown section key in cv_rules – skip, do not invent content.

    return "".join(body_parts)


def cv_css(*, font_b64: str | None = None) -> str:
    return _CSS_TEMPLATE.format(font_b64=font_b64 or _font_base64())


def generate_cv_variant_html(
    selection_plan: SelectionPlan,
    cv_master: CvMaster,
    cv_rules: CvRules,
) -> str:
    """Render a full, styled HTML CV document (single-column, ATS-safe)."""
    content = cv_content_html(selection_plan, cv_master, cv_rules)
    css = cv_css()
    person_name = escape(cv_master.person.name)
    return (
        "<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\">"
        f"<title>{person_name}</title><style>{css}</style></head>"
        f"<body>{content}</body></html>"
    )


def generate_cv_variant_pdf_html(
    selection_plan: SelectionPlan,
    cv_master: CvMaster,
    cv_rules: CvRules,
    out_path: Path | str,
) -> Path:
    """Render the styled HTML CV and print it to PDF via headless Chromium."""
    from playwright.sync_api import sync_playwright

    html = generate_cv_variant_html(selection_plan, cv_master, cv_rules)
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            page.pdf(
                path=str(path),
                format="A4",
                print_background=True,
                margin={"top": "0mm", "bottom": "0mm", "left": "0mm", "right": "0mm"},
            )
        finally:
            browser.close()
    return path
