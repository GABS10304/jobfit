# Score-Diagnose: AI Product Manager (Sourcing Watchlist)

**Datum:** 2026-07-24  
**Sprint:** 7  
**Scope:** Diagnose niedriger Top-Scores bei Multi-Board-Sourcing (FLEX, credium).  
**Nicht geändert:** V3-Schwellen, Scoring-Formel, Ranking-Band, Präsenzlogik.

---

## 1. Kurzfazit

| Frage | Antwort |
|-------|---------|
| Bottleneck Scraper? | **Nein** – Title-Prefilter + Gates liefern passende AI-PM-Titel. |
| Bottleneck Scoring/Profil-Fit? | **Ja** – Top-Scores 32–38 → nach Lexikon-Fix **46/46**, Ziel **75**. |
| Ursache | Mischung aus **Lexikon-Lücken** (JD-Sprache) und **Profil-Unter-/Fehlspezifikation** (viele CV-Tool-Signale im Nenner, die JDs selten nennen). |
| JD-Mismatch? | Teilweise – FLEX (PE/Portfolio) und credium (PropTech/ESG) ≠ GovTech-Schwerpunkt; trotzdem echte AI-PM-JDs. |
| V3-Formel ändern? | **Nein in diesem Sprint.** Empfehlung für späteren Review-Auftrag. |

---

## 2. Referenz-JDs (SoT der Diagnose)

Quelle: `/tmp/multi_board_e2e.json` (Multi-Board-Lauf), Fit-Text wie Sourcing: `fit_check_jd_text` = Title + Location + Work-Mode + Employment + `jd_text`.

| Board | Titel | Gate | Baseline Top | Baseline Rolle |
|-------|-------|------|--------------|----------------|
| flex | AI Product Manager (m/w/d) | `proceed` | **32** | `technical_product_manager` |
| credium | AI Produkt Manager:in … (SaaS) | `verify_product_ownership` | **38** | `ai_product_manager` |

Filter: `weak_score<75` → Watchlist, nicht Pass.

---

## 3. Verbose Fit-Check (Baseline, vor Lexikon-Fix)

Score = `round(100 * matched / total)` über `core_signals_*` der Rolle. Synonyme: `backend/signal_lexicon.py`.

### 3.1 FLEX – `ai_product_manager` **25** (6/24)

**Matched:** `product_discovery`←markt, `ai_use_case_validation`←use-case, `stakeholder_communication`←stakeholder, `requirements_engineering`←anforderungen, `python`, `claude_desktop`←claude  

**Missing (Auswahl):** `mvp_validation`, `experimental_validation`, `data_driven_decision_making`, `product_analytics`, `privacy_by_design`, Domains `b2b_saas`/`govtech`/`regulated_environments`/`enterprise_software`, Tools `sql`/`pandas`/`streamlit`/`langchain`/`ollama`/`bigquery`/`mcp`/`jira_product_discovery`

**Top-Rolle Baseline:** `technical_product_manager` **32** (7/22) – Prototyp/Übersetzer/Python; gleiche Tool-/Domain-Last.

### 3.2 Credium – `ai_product_manager` **38** (9/24)

**Matched:** Skills inkl. Validierung/Machbarkeit/datengetrieben + `b2b_saas`←**SaaS im Titel** + `customer_intelligence`←kunden  

**Missing:** u. a. `regulated_environments` trotz JD-Text „regulatorisch/Regulierung/regelkonform“; fast alle Tools; `govtech`; `privacy_by_design`

### 3.3 Gap zu 75

| Rolle | Signale gesamt | Für Score ≥75 nötig | Baseline matched | Fehlende Treffer |
|-------|----------------|---------------------|------------------|------------------|
| `ai_product_manager` | 24 | ≥18 | FLEX 6 / credium 9 | **+12 / +9** |
| davon Tools | 10 | — | oft 1–2 | Tool-Nenner allein ≈ **−30…−40 Punkte**, wenn JD keine Stack-Namen nennt |

---

## 4. Audit `role_fit_profile` + `cv_master`

### Fakten Profil (`ai_product_manager`)

- Skills (9): Discovery, AI-Use-Case-Validierung, MVP, datengetrieben, Stakeholder, Analytics, RE, Experimente, Privacy – **in cv_master belegt**.
- Domains (5): `b2b_saas`, `govtech`, `regulated_environments`, `enterprise_software`, `customer_intelligence` – **Profil wahr**, aber JDs oft ohne GovTech/DSGVO-Wording.
- Tools (10): sql, python, pandas, streamlit, langchain, ollama, bigquery, mcp, claude_desktop, jira_product_discovery – **CV-Wahrheit**, in Markt-JDs selten als Literal.

### Lexikon-Lücken vs. JD-Sprache (vor Fix)

| JD-Phrase | Signal (erwartbar) | Vorher im Lexikon? |
|-----------|--------------------|--------------------|
| PoC / PoCs | `mvp_validation`, `experimental_validation` | nein |
| Evals | `experimental_validation` | nein |
| RAG / LLM / LLM-Integrationen | `langchain` (CV-Stack) | nein |
| regulatorisch / Regulierung / regelkonform | `regulated_environments` | nein |
| Datenprodukte / Erfolgskriterien / Feedback-Loops | `product_analytics` | nein |
| Userperspektive / Userdenken / Kundenbedürfnisse | `customer_intelligence` | teilweise (nur „kunden“) |
| Software-/Tech-Mittelstand (FLEX) | `enterprise_software` | nein |
| Claude Code | `claude_desktop` | nur „claude“ (substring ok) |

### Lesart

- **Nicht** primär „Kandidat passt nicht zu AI-PM“.
- **Primär:** Matching misst „wie viele *Profil*-Signale die JD wörtlich triggert“ – schwere CV-Tool-Liste + fehlende DE-Synonyme → systematisch niedrige Scores bei echten AI-PM-JDs.
- Evidence-Bullets in `role_fit_profile` beeinflussen den Score **nicht** (nur Explainability/Generation).

---

## 5. Minimaler Daten-Fix (dieser Sprint)

### Erlaubt / gemacht

1. **`backend/signal_lexicon.py`** – Synonyme für bestehende Signal-IDs (keine Formel-/Schwellenänderung).
2. **`domain/role_fit_profile.yaml`** – ein zusätzliches Evidence-Bullet (MCP/Claude-Desktop), bereits in `cv_master` belegt; **Score-neutral**.

### Nicht gemacht (V3 Freeze / Review nötig)

- Keine Änderung an `min_score_for_review` (75) oder Score-Formel.
- Kein Entfernen/Umbauen von `core_signals_tools` (würde Nenner ändern → großer Score-Sprung, Review-Auftrag).
- Keine neuen Signal-IDs ohne Profil-Review.

### Before / After (gleiche zwei JDs, `fit_check_jd_text`)

| Board | Baseline Top | After Top | Delta | After `ai_product_manager` |
|-------|--------------|-----------|-------|----------------------------|
| flex | 32 (`technical_product_manager`) | **46** (`ai_product_manager`) | **+14** | 46 (11/24) |
| credium | 38 (`ai_product_manager`) | **46** (`ai_product_manager`) | **+8** | 46 (11/24) |

Regression: `tests/test_smoke_ref_pack.py`, `test_v3_presence.py`, `test_smoke.py` → **48 passed**.

**Weiterhin unter 75** – Lexikon allein schließt die Lücke nicht.

---

## 6. Empfehlung für späteren Review-Auftrag

1. **Signal-Modell trennen:** CV-Evidence-Tools (streamlit, ollama, mcp, …) nicht 1:1 als JD-Match-Nenner; oder Tools nur scoren, wenn die JD überhaupt Tooling erwähnt.
2. **Domain-Gewichtung / Soft-Domains:** `govtech` nicht hart bestrafen, wenn JD reguliert/PropTech/PE-Software ist.
3. Optional: Title ist bereits in Sourcing-Fit-Text – beibehalten (credium `SaaS` → `b2b_saas`).
4. Schwelle 75 erst anfassen, **nach** Signal-Modell-Review – sonst Watchlist→Pass ohne echten Fit-Gewinn.

**Sprint 8:** Schema/Engine unterstützen **kein** required vs. optional / Tool-Tier → keine Profil-Demotion ohne Formeländerung. Ausarbeiteter Auftrag inkl. Simulation und Acceptance Tests: [`REVIEW_AUFTRAG_TOOL_SIGNALS.md`](REVIEW_AUFTRAG_TOOL_SIGNALS.md).

---

## 7. Nächster Sprint (Vorschlag)

1. Review-Auftrag abarbeiten: [`REVIEW_AUFTRAG_TOOL_SIGNALS.md`](REVIEW_AUFTRAG_TOOL_SIGNALS.md) (Option A empfohlen; C abgelehnt).  
2. Danach erneuter Multi-Board-Lauf + Pass-Rate AI-PM.  
3. Bis dahin: Watchlist + CV-Varianten für weak AI-PM-Matches weiter nutzen.
