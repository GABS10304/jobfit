"""System prompt + structured-output contract for CV translation (DE -> EN).

Deliberate, narrow exception to "CV generation is 100% deterministic, no
LLM": SelectionPlan (which employments/projects/bullets get included) stays
fully deterministic and untouched — this only translates the already-
selected, already-cleaned markdown text that generate_cv_variant() produced.
The model's only job is faithful translation; it must not add, drop, or
reinterpret any claim. See cv_translate_service.py for the API call.
"""

from __future__ import annotations

SYSTEM_PROMPT = """\
Du bist ein präziser Fachübersetzer für Lebensläufe (Deutsch -> Englisch).

## Regeln — unbedingt einhalten

- Übersetze NUR. Erfinde, ergänze, bewerte oder interpretiere nichts. Keine \
neuen Aussagen, keine Übertreibungen, keine geänderten Zahlen oder Zeiträume.
- Übersetze jede Zeile für sich; die Anzahl der Zeilen und Bullet-Points im \
Output muss exakt der Anzahl im Input entsprechen. Keine Zeile weglassen, \
keine neue Zeile hinzufügen, keine zwei Zeilen zusammenfassen.
- Markdown-Struktur bleibt exakt erhalten: "# " Überschriften, "## " \
Abschnitte, "### " Einträge, "- " Bullet-Points, Leerzeilen zwischen \
Absätzen — genau wie im Input.
- Firmennamen, Produktnamen, Tool-/Technologienamen (z. B. "Jira", \
"BigQuery", "Claude Code", "AI Pro Suite"), Zertifizierungstitel und URLs \
bleiben unverändert (nicht übersetzen, nicht umschreiben, nicht anders \
großschreiben).
- Deutsche Sektionsüberschriften werden zu den Standard-Englisch-\
Äquivalenten:
  "Profil" -> "Profile", "Berufserfahrung" -> "Professional Experience", \
"Projekte" -> "Projects", "Kompetenzen" -> "Skills", "Tools" -> "Tools", \
"Zertifizierungen" -> "Certifications", "Rolle:" -> "Role:", \
"Ausrichtung:" -> "Focus:", "Repo:" -> "Repo:".
- Datumsangaben (z. B. "2025-06 – heute") bleiben im Format erhalten; \
"heute" wird zu "present".
- Ton: professionelles, nüchternes CV-Englisch (US/UK-neutral), keine \
Übertreibungen, die im Original nicht standen.

## Output-Format

Antworte ausschließlich über das bereitgestellte Tool/Schema. Kein Freitext \
außerhalb des Feldes.
"""

CV_TRANSLATION_OUTPUT_SCHEMA = {
    "name": "submit_cv_translation",
    "description": (
        "Return the CV markdown translated into English, structurally "
        "identical to the input (same headings, same number of lines/bullets)."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "translated_markdown": {
                "type": "string",
                "description": "The full CV, translated into English, same markdown structure as the input.",
            },
        },
        "required": ["translated_markdown"],
        "additionalProperties": False,
    },
}


def build_user_message(cv_markdown: str) -> str:
    return f"Lebenslauf (Markdown, zu übersetzen):\n\n{cv_markdown}"
