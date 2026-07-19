# Smoke-Test: Grauzonen-JD & Ranking

PM-Pipeline und Flags: siehe [`FIT_LOGIC_NOTES.md`](FIT_LOGIC_NOTES.md).

## Smoke-Test

- **Input:** Eine echte produktnahe Grauzonen-JD mit unklarer Ownership.
- **Erwartung 1:** `status_flag = verify_product_ownership`.
- **Erwartung 2:** `verify = true`.
- **Erwartung 3:** Scoring läuft weiter.
- **Erwartung 4:** Produktrollen liegen bei ähnlichen Scores vor Koordinations- und Coaching-Rollen.
- **Erwartung 5:** Die Top-10-Reihenfolge wirkt fachlich plausibel und nicht rein numerisch.

## Akzeptanzkriterien

- Die Flag-Logik bleibt unverändert.
- Die Ranking-Regel greift nur im vorgesehenen Band (`SIMILAR_SCORE_BAND = 12`).
- Kein Einfluss auf Constraints oder SoT.
- Keine Regression bei klaren Produkt- oder Nicht-Produkt-JDs.

## Kurzform für Doku

Smoke-Test bestanden, wenn eine echte Grauzonen-JD bei unklarer Ownership korrekt auf `verify_product_ownership` geht, weiter gescort wird und Produktrollen im definierten Band vor Koordination/Coaching landen.

## Automatisierte Abdeckung

| Test | Was |
|------|-----|
| `test_fit_check_german_gray_zone_verify_ownership` | Grauzone → verify + Scoring + Ranking |
| `test_reference_case_senior_product_transformation_lead` | Gespeicherter Referenzfall (Hybrid + Transformation Lead) |
| `test_fit_check_with_dummy_jd` | Klare Produkt-JD → `proceed` |
| `test_constraints_non_product_role_is_no_go` / `test_fit_check_no_go_skips_roles` | Nicht-Produkt / Hard-Fail → `no_go` |
| `test_band12_*` | Band-12-Boundaries |
| `test_v3_smoke_grayzone_presence_tradeoff` | Präsenz-Trade-off → sichtbare Ausnahme (V3) |
| `test_smoke_ref_pack_*` | Referenzpaket 4 JDs (`ref_smoke_pack_v3.yaml`) |

## Hinweis

Externe JD-Dateien (z. B. Google Drive) werden nicht automatisch geladen. Referenzfälle liegen unter `domain/fixtures/`.

**Referenzpaket:** Vier Referenz-JDs decken Produkt-Grauzone, starken Produktfit mit mehr Präsenz, koordinationslastigen Fall und Coaching-/Transformation-Fall ab; sie dienen nur als Stabilitätscheck ohne Logikänderung.

