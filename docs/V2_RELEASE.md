# Job Fit System – Version 2

**Status:** V2 review-ready · Tests grün · Freeze nach Review  
**Datum:** 2026-07-19

## Was V2 gegenüber V1 ändert

1. **Regelhygiene:** Soft-Cue `team_coaching_preferred` ohne bare „coaching“/„transformation“; Negationen („ohne reine …“) werden nicht als Match gewertet.
2. **Remote:** `remote_first_hybrid_ok` erkennt explizit „1 Tag pro Woche“ / „bis zu 1 Tag“; ≥2 Präsenztage bleiben No-Go.
3. **Tests:** Szenarien für klare Produkt-/Koord-/Coach-JDs, Ownership klar vs. unklar, Junior-Smoke, Referenzfälle.
4. **Doku/Cursor-Regeln:** V2-Policy und Freeze-Hinweise aktualisiert.

## Unverändert (bewusst)

- Hard-Constraint-IDs und Flag-Semantik (`no_go` / `verify_product_ownership` / `proceed`)
- Ranking-Tier Produkt > Koordination > Coaching (`SIMILAR_SCORE_BAND = 12`)
- SoT-Dateien unter `domain/` (Inhalt nur bei Nutzer-Auftrag)

## Entscheidungslogik (operational)

1. Loader (YAML/JSON SoT)
2. Hard Constraints → Flag
3. Bei `no_go`: stoppen
4. Bei `proceed` / `verify_product_ownership`: scorenen
5. Ranking (Band-12 Tie-Breaker)
6. Response

## Warum so

- **verify statt no_go bei Ownership-Unklarheit:** produktnahe JDs nicht vorschnell verwerfen.
- **Remote-first ≤1 Office-Tag:** Hybrid-Realität abbilden; echte Präsenzpflicht weiter hart.
- **Produkt vor Koord/Coach im Band:** fachliche Priorität in Grauzonen, nicht nur Roh-Score.

## Qualitäts-Checkliste V2

- [x] Kernregeln konsistent
- [x] Boundary-Tests Band 12 + Remote
- [x] Smoke Junior Gray-Zone grün
- [x] Regression Senior-Referenzfall grün
- [x] Doku = tatsächliche Logik

## Freeze (nach Review)

Keine weiteren Regeländerungen ohne neuen Auftrag. Erlaubt: Doku, Referenzfälle, Bugfixes mit Tests.
