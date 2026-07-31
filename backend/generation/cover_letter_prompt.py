"""System prompt + structured-output contract for the automated cover-letter
service (Phase 1 SaaS blocker).

This replaces "Claude writes the Anschreiben live in the approval chat" with
a Claude API call the backend can make on its own. It is the cv-tailor
SKILL.md (Documents/cv-software/.claude/skills/cv-tailor/) translated from an
interactive skill (asks the human follow-up questions) into a non-interactive
system prompt (must work from the input alone, in one call).

Key differences from the interactive skill:
- No "frag den User"/Rückfrage steps — there is no human to ask mid-generation.
  Anything that would have been a clarifying question becomes an entry in the
  `flags` output field instead, surfaced to the paying customer in the review
  UI (the customer is the human-in-the-loop now, not Gabriel/Claude Code).
- Only pre-filtered facts are ever in context: the caller must strip any
  master-cv bullet tagged [TODO] or unconfirmed before building the prompt
  input — the model is never shown a claim it must decide whether to trust.
- Output is structured (tool-use / forced JSON), not free text, so the
  backend can render it deterministically (same DIN-5008 renderer as
  backend/generation/application_pdf.py) instead of parsing prose.

The actual API call lives in backend/generation/cover_letter_service.py.
Not implemented here or there yet: the automated groundedness check (a
second, cheaper call that extracts claims from the draft and verifies each
against the input facts — recommended before this goes live).
"""

from __future__ import annotations

SYSTEM_PROMPT = """\
Du bist ein erfahrener Senior-Recruiter und Bewerbungs-Stratege. Du schreibst \
ein einzelnes Anschreiben (Motivationsschreiben) für eine konkrete Bewerbung, \
basierend ausschließlich auf den Fakten, die dir im Input gegeben werden.

## Faktenquelle — nicht verhandelbar

Du bekommst im Input:
- Die Job Description (JD) im Volltext.
- Eine kuratierte Liste belegter Fakten aus dem Master-CV der Person \
(Stationen, Kennzahlen, Projekte) — bereits gefiltert auf "belegt" oder \
"teilweise belegt". Unbelegte oder offene Punkte sind hier nie enthalten.
- Die vom Fit-Check ermittelten am besten passenden Kompetenz-Signale.

Du erfindest **niemals** eine Tätigkeit, Zahl, Kunde, Firma oder einen \
Zeitraum, der nicht wörtlich oder sinngemäß in den gegebenen Fakten steht. \
Wenn die JD etwas verlangt, das in den gegebenen Fakten fehlt: baue **keine** \
Behauptung dazu, sondern trage einen Eintrag in `flags` ein (siehe \
Output-Format) und lass die Lücke im Anschreiben entweder unerwähnt oder \
adressiere sie ehrlich als offenen Punkt — nie als erfundene Kompetenz.

Widersprüchliche Fakten im Input (z. B. zwei unterschiedliche Werte für \
dieselbe Kennzahl) werden nicht selbst aufgelöst — auch das wird als `flags`-\
Eintrag gemeldet, mit der unsicheren Stelle klar benannt.

## Aufbau

Klassischer DIN-5008-Brief:
1. Absender (Name, Ort) und Empfänger (Firma, ggf. Ansprechperson, Ort) als \
separate Blöcke.
2. Ort/Datum, Betreffzeile ("Bewerbung als <Rolle>").
3. Anrede ("Sehr geehrte/r Frau/Herr <Name>," falls Ansprechperson bekannt, \
sonst "Sehr geehrte Damen und Herren,").
4. 3–4 Absätze:
   - Aufhänger: idealerweise mit Bezug auf eine Formulierung/ein Thema aus \
der JD selbst — kein generischer Einstieg.
   - 1–2 Absätze mit konkreten, belegten Erfahrungen, die die wichtigsten \
Anforderungen der JD spiegeln.
   - Optional: ehrliche, kurze Adressierung einer offensichtlichen Lücke \
(z. B. fehlende formale Qualifikation), nur wenn die Fakten das hergeben — \
sonst weglassen.
5. Abschluss mit Gesprächsangebot, Grußformel.

**Vermeiden:** schwache Zeitangaben, die Erfahrung kleiner wirken lassen als \
sie ist (z. B. "seit über einem Jahr", wenn die Gesamterfahrung im Themenfeld \
länger ist) — stattdessen auf die breitere Erfahrung referenzieren, sofern \
durch die gegebenen Fakten gedeckt.

## Stil (93-%-Regel — menschlich, nicht steril)

- Satzlängen variieren: kurze Sätze neben längeren, nie mehrere gleich \
gebaute Sätze hintereinander.
- Verben variieren, kein Verb mehr als zweimal im gesamten Text.
- KI-Klischees streichen: "leidenschaftlich", "nahtlos", "maßgeblich \
vorangetrieben", "synergetisch", Gedankenstrich-Ketten.
- **Kein Gedankenstrich (—).** Stattdessen ein einfacher Bindestrich mit \
Leerzeichen ( - ) für Einschübe.
- Zielbegriffe aus der JD spiegeln (exakte Tool-/Methodennamen übernehmen), \
aber Phrasen nicht wörtlich papageienhaft wiederholen.
- Aktiv statt Passiv, Wirkung vor reiner Tätigkeitsbeschreibung.
- Keine echten Rechtschreib- oder Grammatikfehler.

## Output-Format

Antworte ausschließlich über das bereitgestellte Tool/Schema (siehe \
`COVER_LETTER_OUTPUT_SCHEMA`). Kein Freitext außerhalb der Felder. Das \
`flags`-Feld ist die einzige Stelle für Unsicherheiten, offene Lücken oder \
Widersprüche — es ersetzt die Rückfrage an einen Menschen, die es in dieser \
automatisierten Verwendung nicht geben kann.
"""


COVER_LETTER_OUTPUT_SCHEMA = {
    "name": "submit_cover_letter",
    "description": (
        "Return the drafted cover letter as structured fields, plus any "
        "flags for the human reviewer (gaps, ambiguous facts, contradictions "
        "in the input that were not invented around, only surfaced)."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "sender_block": {
                "type": "string",
                "description": "Name + Ort des Absenders, zeilenweise.",
            },
            "recipient_block": {
                "type": "string",
                "description": "Firma, ggf. Ansprechperson, Ort, zeilenweise.",
            },
            "date_line": {
                "type": "string",
                "description": "z. B. 'Marktheidenfeld, 31. Juli 2026'.",
            },
            "subject_line": {
                "type": "string",
                "description": "z. B. 'Bewerbung als Senior Product Manager (m/w/d)'.",
            },
            "salutation": {"type": "string"},
            "paragraphs": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 4,
                "description": "3-4 Absätze, siehe Aufbau-Regeln im System-Prompt.",
            },
            "closing_line": {
                "type": "string",
                "description": "z. B. 'Mit freundlichen Grüßen'.",
            },
            "signature": {"type": "string"},
            "flags": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["gap", "ambiguous_fact", "contradiction"],
                        },
                        "description": {
                            "type": "string",
                            "description": (
                                "Was genau unsicher/offen ist, für die "
                                "Review-UI des Kunden."
                            ),
                        },
                    },
                    "required": ["type", "description"],
                    "additionalProperties": False,
                },
            },
        },
        "required": [
            "sender_block",
            "recipient_block",
            "date_line",
            "subject_line",
            "salutation",
            "paragraphs",
            "closing_line",
            "signature",
            "flags",
        ],
        "additionalProperties": False,
    },
}


def build_user_message(context: dict) -> str:
    """Build the user-turn content from prepare_application_draft.py's context.json.

    The fact source is `cv_markdown` — the CV already rendered by
    generate_cv_variant() from the SelectionPlan. That rendering already
    applies the evidence-strength gate (cv_rules.evidence.min_strength_for_inclusion)
    and strips [TODO]/provenance tags (see backend/generation/cv_variant.py),
    so it is exactly the "already filtered, verified facts" the system prompt
    requires — no separate filtering step needed here.
    """
    return (
        f"Job Description:\n{context['jd_text']}\n\n"
        f"Firma: {context.get('company', '?')}\n"
        f"Zielrolle: {context.get('title', '?')}\n\n"
        f"Gematchte Kompetenz-Signale: {', '.join(context.get('matched_signals', []))}\n"
        f"Fehlende Signale (nicht erfinden, ggf. als flag melden): "
        f"{', '.join(context.get('missing_signals', []))}\n\n"
        f"Belegte Fakten (bereits gefilterter, gerenderter CV):\n"
        f"{context.get('cv_markdown', '<vom Aufrufer einzufügen>')}\n\n"
        f"Person: {context.get('person_name', '?')}, "
        f"{context.get('person_location', '?')}\n"
    )
