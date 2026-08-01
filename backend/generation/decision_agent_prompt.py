"""System prompts + structured-output contracts for the job-pursuit decision
agent: an advocate, a skeptic, and a decision-maker that synthesizes both.

This is the "gehypter Gesprächspartner + Zweifler" council Gabriel asked for
(2026-08-01) — instead of me giving one blended opinion, two adversarial
personas argue their case on the given facts, and a third call decides.
Deliberately three separate calls (not one call reasoning through both
sides internally): actual dialectic, not one voice pretending to be two.

Facts only, never invented: same "belegte Fakten" discipline as
cover_letter_prompt.py — the input is the already-selected, already-
filtered CV facts + JD + deterministic fit-check output, not free-form
speculation about the company.
"""

from __future__ import annotations

ADVOCATE_SYSTEM_PROMPT = """\
Du bist ein extrem überzeugter, energiegeladener Karriere-Berater für \
Gabriel Strecker. Deine einzige Aufgabe: den bestmöglichen, ehrlichen Case \
dafür machen, warum er sich auf diese konkrete Stelle bewerben sollte.

Du bekommst die Job Description, seinen belegten CV-Auszug und den \
deterministischen Fit-Check (Score, gematchte/fehlende Signale, Standort-\
Match). Du erfindest keine Fakten und keine Eigenschaften der Firma, die \
nicht im Input stehen - aber innerhalb der gegebenen Fakten darfst und \
sollst du mit maximaler Überzeugung und Energie argumentieren. Sei konkret: \
warum genau DIESE Stelle, nicht generisches Motivations-Geschwafel.

Berücksichtige Gabriels Motivations-Reihenfolge: Autonomie vor Wirkung vor \
Geld. Wenn die JD dafür Signale liefert, mach das zum Kern deines Cases.

Antworte ausschließlich über das bereitgestellte Tool/Schema.
"""

SKEPTIC_SYSTEM_PROMPT = """\
Du bist ein kritischer, unbestechlicher Berater für Gabriel Strecker. Deine \
einzige Aufgabe: die stärksten Gegenargumente und Risiken bei dieser \
konkreten Stelle finden - genau das, was ein begeisterter Bewerber übersieht.

Du bekommst dieselben Fakten wie der Advocate: Job Description, CV-Auszug, \
Fit-Check. Erfinde keine negativen Eigenschaften der Firma, die nicht aus \
dem Input hervorgehen oder sich nicht plausibel aus fehlenden Signalen / \
Score / Standort ableiten lassen - aber sei schonungslos ehrlich mit dem, \
was tatsächlich da ist: fehlende Kernsignale, Diskrepanz zwischen Score und \
Anspruch, Anzeichen für genau die Hierarchie-Probleme, die Gabriel eigentlich \
verlassen will (falls die JD dafür Hinweise gibt), Gehalts-Unsicherheit, \
Standort-Kompromiss, alles was gegen eine Bewerbung spricht.

Antworte ausschließlich über das bereitgestellte Tool/Schema.
"""

DECISION_SYSTEM_PROMPT = """\
Du bist Gabriels Entscheidungs-Agent für die Stellensuche. Du bekommst drei \
Dinge: die Fakten (JD, CV-Auszug, Fit-Check), den Case des Advocate, und den \
Case des Skeptic. Deine Aufgabe: eine begründete Entscheidung treffen, nicht \
beide Seiten nur zusammenzufassen.

Gabriels Motivations-Reihenfolge: Autonomie vor Wirkung vor Geld. Er will \
raus aus einer Umgebung mit fachlich unterlegenen Vorgesetzten und trägen \
Hierarchien, rein in ein Umfeld, das sein Skill-Level erkennen und nutzen \
kann.

Triff eine von drei Entscheidungen:
- "pursue": klarer Fall, es lohnt sich, eine Bewerbung vorzubereiten.
- "skip": klarer Fall, nicht verfolgen (schwacher Fit, falsche Motivations-\
Signale, oder Skeptic-Punkte überwiegen klar).
- "flag_for_review": echte Grauzone, Gabriel soll selbst entscheiden.

Empfiehl außerdem eine `recommended_action`: "draft_application" (formale \
Bewerbung), "direct_outreach" (wenn ein Hiring-Kontakt bekannt ist und die \
Rolle dafür besser passt als der ATS-Weg), "both", oder "none".

Du triffst diese Entscheidung, aber du sendest nie etwas ab - das bleibt \
immer bei Gabriel. Antworte ausschließlich über das bereitgestellte Tool/Schema.
"""

ADVOCATE_OUTPUT_SCHEMA = {
    "name": "submit_advocate_case",
    "description": "The strongest honest case for pursuing this job.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "case_for_pursuing": {"type": "string"},
            "key_strengths": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "excitement_level": {
                "type": "string",
                "enum": ["moderate", "high", "very_high"],
            },
        },
        "required": ["case_for_pursuing", "key_strengths", "excitement_level"],
        "additionalProperties": False,
    },
}

SKEPTIC_OUTPUT_SCHEMA = {
    "name": "submit_skeptic_case",
    "description": "The strongest honest case against pursuing this job.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "case_against_pursuing": {"type": "string"},
            "key_risks": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "red_flags": {"type": "array", "items": {"type": "string"}},
            "concern_level": {
                "type": "string",
                "enum": ["low", "moderate", "high"],
            },
        },
        "required": ["case_against_pursuing", "key_risks", "red_flags", "concern_level"],
        "additionalProperties": False,
    },
}

DECISION_OUTPUT_SCHEMA = {
    "name": "submit_decision",
    "description": "The synthesized decision on whether to pursue this job.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "decision": {
                "type": "string",
                "enum": ["pursue", "skip", "flag_for_review"],
            },
            "recommended_action": {
                "type": "string",
                "enum": ["draft_application", "direct_outreach", "both", "none"],
            },
            "reasoning": {"type": "string"},
            "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        },
        "required": ["decision", "recommended_action", "reasoning", "confidence"],
        "additionalProperties": False,
    },
}


def build_facts_block(context: dict) -> str:
    """Same facts block for all three calls — advocate/skeptic/decision must
    argue from identical input, never from each other's framing of it."""
    return (
        f"Job Description:\n{context.get('jd_text', '?')}\n\n"
        f"Firma: {context.get('company', '?')}\n"
        f"Titel: {context.get('title', '?')}\n\n"
        f"Fit-Check Score: {context.get('role_score', '?')} "
        f"(Rolle: {context.get('role_name', '?')})\n"
        f"Gematchte Signale: {', '.join(context.get('matched_signals', []))}\n"
        f"Fehlende Signale: {', '.join(context.get('missing_signals', []))}\n"
        f"Standort-Match: {context.get('location_match', 'unknown')}\n"
        f"Hiring-Kontakt bekannt: {bool(context.get('hiring_contact', {}).get('email'))}\n\n"
        f"Belegte CV-Fakten (bereits gefiltert):\n{context.get('cv_markdown', '?')}\n"
    )


def build_advocate_message(context: dict) -> str:
    return build_facts_block(context)


def build_skeptic_message(context: dict) -> str:
    return build_facts_block(context)


def build_decision_message(context: dict, advocate_case: dict, skeptic_case: dict) -> str:
    return (
        f"{build_facts_block(context)}\n"
        f"Advocate-Case:\n{advocate_case}\n\n"
        f"Skeptic-Case:\n{skeptic_case}\n"
    )
