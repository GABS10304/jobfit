# Fixtures

Betriebs- und Referenzfälle für Review und Alltag. **Nur dokumentieren / stabil prüfen – keine Logikänderung daraus ableiten.**

## TeamViewer – AI Product / Discovery-nah
- Ergebnis: `verify_product_ownership`
- Präsenz: `remote_first_ok` / `ok`
- Sales-Gate: passed
- Ownership: unclear → Verify
- Status: realer Betriebsfall, nur dokumentieren
- Dateien: `ops_teamviewer_ai_product_discovery_hybrid.md` · `.yaml`

## Starke Produktrolle mit mehr Präsenz
- Ergebnis: `verify_product_ownership`
- Präsenz: `exception_granted` möglich
- Ownership: unklar bis implizit
- Status: Grauzonenfall, nur bei hohem Fit
- Datei: `ops_strong_product_more_presence.md`

## Koordinationslastige Rolle mit Produktanteil
- Ergebnis: `verify_product_ownership`
- Präsenz: hybrid / flexibel
- Ownership: unklar
- Status: Grauzonenfall, sauber klären
- Datei: `ops_coordination_with_product_share.md`

---

## Weitere Referenzen

| Datei | Zweck |
|-------|--------|
| `ref_smoke_pack_v3.yaml` | 4 Smoke-JDs mit Erwartungswerten (Stabilitätscheck) |
| `ref_junior_product_transformation_lead_remote_first.yaml` | Junior Grauzone, ≤1 Office-Tag |
| `ref_senior_product_transformation_lead_hybrid.yaml` | Senior Hybrid Grauzone |

PM-Übersicht: `docs/FIT_LOGIC_NOTES.md`
