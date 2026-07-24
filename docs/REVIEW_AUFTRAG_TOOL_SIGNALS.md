# Review-Auftrag: Tool-Signale vs. JD-Match-Nenner

**Datum:** 2026-07-24  
**Sprint:** 8  
**Status:** Auftrag (keine Implementierung)  
**V3 Freeze:** Schwellen und Score-Formel unverändert. Option C (Schwelle senken) ist abgelehnt.

Bezug: [`SCORE_DIAGNOSIS_AI_PM.md`](SCORE_DIAGNOSIS_AI_PM.md) (Sprint 7, Lexikon-Fix → Top-Score 46).

---

## 1. Problem

### Fakt (Engine)

- Score = `round(100 * matched / total)` über die flache Vereinigung von `core_signals_skills` ∪ `core_signals_domains` ∪ `core_signals_tools` (`backend/fit_engine.py` → `_all_signals` / `score_role`).
- `RoleSignals` (`backend/models.py`) hat **keine** Felder für `required` / `optional`, keine Signal-Gewichte, keine Tool-Tier.
- `ROLE_RANK_TIER` betrifft nur Rollen-Ranking bei ähnlichen Scores, nicht den Signal-Nenner.
- Soft-Constraint-`weight` gilt nur für Constraints, nicht für Role-Fit-Signale.

### Fakt (Profil AI-PM)

- `ai_product_manager`: 9 Skills + 5 Domains + **10 Tools** = 24 Signale.
- Tools sind weitgehend **CV-Stack-Wahrheit** (streamlit, ollama, mcp, langchain, …), die Markt-JDs selten literal nennen.
- Nach Sprint-7-Lexikon: FLEX und credium jeweils **11/24 = 46**; für ≥75 braucht es ≥18 Treffer (Gap +7).

### Lesart

Der Nenner misst „wie viele *Profil*-Signale die JD triggert“, nicht „wie gut der Kandidat zur Rolle passt“. Reine Tooling-Signale blähen den Nenner auf und halten echte AI-PM-JDs systematisch unter der Review-Schwelle 75.

### Sprint-8-Entscheidung

**Schema unterstützt optional/tool-tier nicht.** Profil-only „Demote“ ohne Formel-/Schema-Änderung wäre nur:

- Signale aus `core_signals_tools` **löschen** (kein Optional, sondern Entfernen), oder
- Signale in unscored Felder verschieben (Evidence) – gleichbedeutend mit Entfernen aus dem Score.

Beides ändert den Nenner still und braucht Review (bereits Sprint 7: kein Umbau von `core_signals_tools` ohne Auftrag). **Daher: keine Implementierung in Sprint 8.**

---

## 2. Optionen

| Option | Inhalt | Formel? | Schema? | V3-Schwelle? |
|--------|--------|---------|---------|--------------|
| **A** | Optional-Tools im Profil: required = Skills+Domains (+ ggf. marktübliche Tools); optional Tools nur Bonus / nicht im Nenner wenn unmatched | ja (oder neue Semantik) | ja (`optional_signals_tools` o.ä.) | nein |
| **B** | Match-Formel splitten: z. B. Skills/Domains Gewicht 1, Tools Gewicht ≪1; oder getrennte Teil-Scores | ja | optional | nein |
| **C** | `min_score_for_review` senken | nein | nein | **ja – abgelehnt** (Watchlist→Pass ohne Fit-Gewinn; Freeze) |

### A – Optional Tools im Profil (empfohlen)

- SoT bleibt Profil-YAML; Engine respektiert required vs. optional.
- Variante A0: optional unmatched → nicht im Nenner; matched optional → optional Bonus (num+den) oder reiner Bonus-Cap.
- Variante A1: alle Tools optional; nur Skills+Domains required.

### B – Split / Gewichtung

- Keine Profil-Semantik „optional“, aber Tool-Kategorie gewichtet (z. B. 0.25).
- Weniger erklärbar für PM; schwerer zu auditieren als explizites optional.

### C – Schwelle senken

- **Reject.** Kaschiert Modellfehler; verletzt V3-Freeze-Intent.

---

## 3. Simulierte Score-Wirkung (keine Code-Änderung)

Messbasis: `/tmp/multi_board_e2e.json`, Fit-Text wie Sourcing (`title` + `location` + `work_mode` + `employment_type` + `jd_text`). Lexikon-Stand nach Sprint 7.

### 3.1 `ai_product_manager`

| JD | IST (alle Signale) | A: Tools aus Nenner | A′: + matched Tools als Bonus | B: Tools ×0.25 | Demote nur „pure“ Tools\* |
|----|--------------------|---------------------|-------------------------------|----------------|---------------------------|
| FLEX AI-PM | **46** (11/24) | **57** (8/14) | **65** | **53** | **53** (9/17) |
| credium AI-PM | **46** (11/24) | **79** (11/14) | **79** | **67** | **65** (11/17) |

\*Pure = streamlit, langchain, ollama, mcp, claude_desktop, pandas, bigquery; required bleiben sql, python, jira_product_discovery.

Matched IST (kurz):

- **FLEX:** Skills Discovery/Use-Case/MVP/Stakeholder/RE/Experimente; Domains enterprise + customer_intelligence; Tools python, langchain, claude_desktop. Fehlend u. a. data_driven, analytics, privacy; Domains b2b_saas/govtech/regulated.
- **credium:** 8/9 Skills (nur privacy fehlt); Domains b2b_saas, regulated, customer_intelligence; **0 Tools**. Fehlend govtech, enterprise_software.

### 3.2 Erreichbarkeit 75

| Szenario | FLEX ≥75? | credium ≥75? |
|----------|-----------|--------------|
| IST / Profil-Tools unverändert | nein | nein |
| A (alle Tools optional/aus Nenner) | **nein** (57, Gap 3 Skills/Domains) | **ja** (79) |
| A′ Bonus matched Tools | nein (65) | ja (79) |
| B Gewicht 0.25 | nein | nein |
| Nur pure Tools demoten | nein | nein |
| Tools aus YAML löschen (= A ohne Optional-Semantik) | wie A | wie A |

**Fazit Simulation:** Auch mit Tool-Nenner-Entlastung erreicht **nicht jede** echte AI-PM-JD 75. Credium schon bei A; FLEX bleibt domain/skill-gap-begrenzt (`b2b_saas`/`govtech`/`regulated` bzw. fehlende Skills). Profil-only Löschen ohne Schema wäre zudem undokumentierte Semantik und für FLEX unzureichend.

Analog: `technical_product_manager` hat 9 ähnliche Stack-Tools – gleiches Strukturproblem; Simulation FLEX 41→54 (A), credium 36→62 (A) – beide unter 75.

---

## 4. Empfehlung

1. **Option A** umsetzen (Review + kleines Schema): z. B. `core_signals_tools_optional` oder Flag pro Signal; Engine: required-only Nenner, optional matched als Bonus (A′ bevorzugt, damit genannte Tools nicht bestrafen und helfen).
2. **Nicht** Option C.
3. Option B nur falls Profil-YAML stabil bleiben soll und Gewichte zentral in Code/Config liegen sollen – sekundär zu A.
4. Parallel (separater, kleiner Lexikon-/Domain-Auftrag): FLEX-artige PE/Portfolio-JDs – prüfen ob `b2b_saas`/`enterprise` Synonyme reichen; **keine** Threshold-Änderung.
5. Acceptance erst grün, wenn A (oder B) + ggf. gezielte Synonyme FLEX und credium konsistent ≥75 **oder** dokumentierte Rest-Lücke bewusst Watchlist bleibt.

---

## 5. Acceptance Tests (für spätere Implementierung)

1. **Schema:** Profil mit optionalen Tools lädt; alte Profile ohne optional-Feld verhalten sich **bit-identisch** zum V3-IST (Regression Ref-Pack / Smoke).
2. **Nenner:** Unmatched optional Tool erhöht `total` nicht; Score steigt nicht durch bloßes Fehlen.
3. **Bonus:** Matched optional Tool darf Score nicht senken; bei A′ Score ≥ required-only Score.
4. **Referenz-JDs:** FLEX + credium AI-PM – dokumentierte before/after-Tabelle; Zielband nach A′ mindestens credium ≥75; FLEX Gap explizit messen.
5. **Freeze:** `min_score_for_review=75`, `min_score_for_auto_apply=90`, Ranking-Band 12, Präsenzlogik unverändert.
6. **Keine stillen Demo-Fallbacks;** Explainability: `matched_signals` / `missing_signals` kennzeichnen optional vs. required (oder getrennte Listen).

---

## 6. Out of Scope dieses Auftrags

- Lexikon-Erweiterungen (Sprint 7 erledigt, Nachzüge separat).
- Schwellen, Presence, Ownership-Gates.
- Entfernen von Tool-IDs aus dem Profil ohne Optional-Semantik.
