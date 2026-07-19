# Job Fit System – Version 1 Abschluss & Freeze

**Status:** V1 fertig · Tests grün · Freeze aktiv  
**Datum:** 2026-07-19

## Abschlussnotiz (Team)

- **Version 1 ist fertig.**
- Hard Gates, Ownership-Flag, Remote-Regel und Ranking sind mit Tests abgesichert.
- Der letzte Smoke-Test mit der Junior Product / Transformation Lead-JD ist grün.
- Produktrollen werden im Graubereich korrekt vor Koordination/Coaching priorisiert.
- Ab jetzt nur noch Doku, Referenzfälle und Bugfixes bei echtem Bedarf.

## Freeze-Anweisung

- **Keine weiteren Regeländerungen in Version 1.**
- Neue Änderungen nur nach neuem Bedarf und mit passenden Tests.
- Kernlogik bleibt bis auf Weiteres eingefroren.

## Kurzform

- **V1 steht.**
- **Tests grün.**
- **Freeze aktiv.**

## V1-Kern (eingefroren)

| Baustein | Ort |
|----------|-----|
| SoT | `domain/cv_master.yaml\|json`, `role_fit_profile.yaml`, `constraints.yaml` |
| Hard Gates | `remote_first_hybrid_ok`, `no_hard_sales`, `product_ownership_required` |
| Flags | `no_go` · `verify_product_ownership` · `proceed` |
| Scoring | DE-Synonyme in `backend/signal_lexicon.py` |
| Ranking | Produkt > Koordination > Coaching (`SIMILAR_SCORE_BAND = 12`) |
| Referenzfall | `domain/fixtures/ref_senior_product_transformation_lead_hybrid.yaml` |

## Erlaubt ohne Freeze-Bruch

- Dokumentation
- Weitere Referenzfälle / Smoke-JDs speichern
- Bugfixes bei nachgewiesenem Fehlverhalten (mit Tests)

## Nicht ohne neuen Auftrag

- Änderung an Constraint-/Flag-/Ranking-Semantik
- Erweiterung der Fit-Logik (Phase 2+)
- Scraping, Auto-Apply, Browser-Automation
