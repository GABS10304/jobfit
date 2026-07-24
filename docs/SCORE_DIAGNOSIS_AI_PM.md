# Score-Diagnose: AI Product Manager (Sourcing Watchlist)

**Datum:** 2026-07-24  
**Sprint:** 7 (Diagnose + Lexikon) → 9 (Option A′ optional Tools)  
**Scope:** Diagnose niedriger Top-Scores bei Multi-Board-Sourcing (FLEX, credium).  
**Nicht geändert:** V3-Schwellen (`min_score_for_review=75`), Ranking-Band, Präsenzlogik.

---

## 1. Kurzfazit

| Frage | Antwort |
|-------|---------|
| Bottleneck Scraper? | **Nein** – Title-Prefilter + Gates liefern passende AI-PM-Titel. |
| Bottleneck Scoring/Profil-Fit? | **Teilweise behoben (Sprint 9)** – Tool-Nenner entlastet; credium ≥75, FLEX weiter unter 75. |
| Ursache (Sprint 7) | Lexikon-Lücken + CV-Tool-Signale im Nenner. |
| V3-Schwelle senken? | **Nein** (Option C abgelehnt). |

---

## 2. Referenz-JDs (SoT der Diagnose)

Quelle: `/tmp/multi_board_e2e.json` (Multi-Board-Lauf), Fit-Text wie Sourcing: `fit_check_jd_text` = Title + Location + Work-Mode + Employment + `jd_text`.

| Board | Titel | Gate | Baseline Top (vor Lexikon) | Baseline Rolle |
|-------|-------|------|----------------------------|----------------|
| flex | AI Product Manager (m/w/d) | `proceed` | **32** | `technical_product_manager` |
| credium | AI Produkt Manager:in … (SaaS) | `verify_product_ownership` | **38** | `ai_product_manager` |

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
- **Primär (Sprint 7):** Matching misst „wie viele *Profil*-Signale die JD wörtlich triggert“ – schwere CV-Tool-Liste + fehlende DE-Synonyme.
- Evidence-Bullets in `role_fit_profile` beeinflussen den Score **nicht** (nur Explainability/Generation).

---

## 5. Sprint 7 – Minimaler Daten-Fix

### Erlaubt / gemacht

1. **`backend/signal_lexicon.py`** – Synonyme für bestehende Signal-IDs (keine Formel-/Schwellenänderung).
2. **`domain/role_fit_profile.yaml`** – ein zusätzliches Evidence-Bullet (MCP/Claude-Desktop), bereits in `cv_master` belegt; **Score-neutral**.

### Nicht gemacht in Sprint 7

- Keine Änderung an `min_score_for_review` (75).
- Kein Umbau von `core_signals_tools` (→ Review-Auftrag Sprint 8/9).

### Before / After Lexikon (gleiche zwei JDs)

| Board | Baseline Top | After Lexikon Top | Delta | After `ai_product_manager` |
|-------|--------------|-------------------|-------|----------------------------|
| flex | 32 (`technical_product_manager`) | **46** (`ai_product_manager`) | **+14** | 46 (11/24) |
| credium | 38 (`ai_product_manager`) | **46** (`ai_product_manager`) | **+8** | 46 (11/24) |

**Weiterhin unter 75** – Lexikon allein schließt die Lücke nicht.

---

## 6. Sprint 9 – Option A′ (optional Tools)

Auftrag: [`REVIEW_AUFTRAG_TOOL_SIGNALS.md`](REVIEW_AUFTRAG_TOOL_SIGNALS.md).

- Schema: `optional_signals_tools`; Engine A′ (matched optional = Bonus num+den; unmatched optional ≠ Nenner).
- `ai_product_manager` + `technical_product_manager`: Tools nach `optional_signals_tools`.
- Schwelle unverändert **75**.

### Before / After Option A′

| Board | After Lexikon (Sprint 7) | After A′ (Sprint 9) | ≥75? |
|-------|--------------------------|---------------------|------|
| flex | 46 (11/24) | **65** (8/14 req + 3 opt → 11/17) | nein |
| credium | 46 (11/24) | **79** (11/14 req) | **ja** |

**Ergebnis:** credium AI-PM passiert Review-Schwelle; FLEX bleibt Watchlist (Domain/Skill-Gap, nicht Tool-Nenner).

---

## 7. Nächster Schritt

1. Gezielte Lexikon-/Domain-Synonyme für FLEX-PE/Portfolio-JDs (separater Auftrag).  
2. Kein Senken von `min_score_for_review`.  
3. Multi-Board-Lauf erneut für Pass-Rate AI-PM.
