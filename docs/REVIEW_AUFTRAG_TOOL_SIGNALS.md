# Review-Auftrag: Tool-Signale vs. JD-Match-Nenner

**Datum:** 2026-07-24  
**Sprint:** 9 (Implementierung Option A′) / Auftrag ursprünglich Sprint 8  
**Status:** Option A′ umgesetzt  
**V3 Freeze:** `min_score_for_review=75`, `min_score_for_auto_apply=90`, Ranking-Band 12, Präsenzlogik unverändert. Option C abgelehnt.

Bezug: [`SCORE_DIAGNOSIS_AI_PM.md`](SCORE_DIAGNOSIS_AI_PM.md).

---

## 1. Problem (kurz)

Score = `round(100 * matched / total)` über Profil-Signale. CV-Stack-Tools in `core_signals_tools` blähten den Nenner auf, obwohl Markt-JDs sie selten nennen → echte AI-PM-JDs systematisch unter 75.

---

## 2. Umsetzung Sprint 9 – Option A′

### Schema

- `RoleSignals.optional_signals_tools` (`backend/models.py`), Default `[]`.
- Profile ohne Feld bleiben **bit-identisch** zum V3-IST (nur `core_signals_*` im Nenner).
- Explainability: `RoleFitResult.matched_optional_signals` / `missing_optional_signals`; `missing_signals` = nur required.

### Formel (A′)

- **Required** = `core_signals_skills` ∪ `core_signals_domains` ∪ `core_signals_tools`
- **Optional** = `optional_signals_tools`
- `numerator = matched_required + matched_optional`
- `denominator = len(required) + len(matched_optional)`  
  → unmatched optional **nicht** im Nenner; matched optional als Bonus (num+den).

### Profil

| Rolle | Änderung |
|-------|----------|
| `ai_product_manager` | 10 Tools → `optional_signals_tools`; `core_signals_tools: []` |
| `technical_product_manager` | 9 Tools → `optional_signals_tools`; `core_signals_tools: []` |
| alle anderen | unverändert (Tools required) |

### Freeze

- `min_score_for_review` bleibt **75** (kein Option C).

---

## 3. Messung After (gleiche Fit-Texte wie Sourcing)

Quelle: `/tmp/multi_board_e2e.json` Watchlist, `fit_check_jd_text`.

| JD | Before (Sprint 7, alle Signale) | After A′ | ≥75? |
|----|---------------------------------|----------|------|
| FLEX AI-PM | **46** (11/24) | **65** (8/14 required + 3 optional → 11/17) | **nein** |
| credium AI-PM | **46** (11/24) | **79** (11/14 required + 0 optional) | **ja** |

TPM analog: FLEX **60**, credium **62** (beide unter 75).

**Pass ≥75:** nur **credium** AI-PM. FLEX bleibt Watchlist (Skill/Domain-Gap: u. a. `data_driven`, `product_analytics`, `privacy`, `b2b_saas`/`govtech`/`regulated`).

Entspricht der Sprint-8-Simulation A′.

---

## 4. Acceptance (Sprint 9)

| # | Kriterium | Status |
|---|-----------|--------|
| 1 | Schema lädt; Profile ohne optional bit-identisch | ok (Unit + andere Rollen) |
| 2 | Unmatched optional erhöht `total` nicht | ok |
| 3 | Matched optional senkt Score nicht vs. required-only | ok |
| 4 | FLEX/credium before/after dokumentiert; credium ≥75 | ok |
| 5 | Schwellen/Band/Präsenz unverändert | ok |
| 6 | Explainability optional vs. required | ok (eigene Listen) |

Referenz-Fixture `ref_senior_product_transformation_lead_hybrid`: Top-3 angepasst (AI-PM/TPM steigen ohne Tool-Nenner); Band-12-Assertion PTL vor Agile Project Lead bleibt.

---

## 5. Nächster sinnvoller Schritt

Separater Lexikon-/Domain-Auftrag für FLEX-artige PE/Portfolio-JDs (`b2b_saas`/`enterprise`-Synonyme), **ohne** Threshold-Änderung. Ziel: FLEX Gap zu 75 schließen oder bewusst als Watchlist belassen.
