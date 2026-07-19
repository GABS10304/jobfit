# V3 Freeze

**Freeze aktiv. V3 freigegeben.**  
**Datum:** 2026-07-19

## Ansage

- V3 ist review-ready und wird eingefroren.
- Präsenzregel, Boundary-Tests, Ausnahme-Logik und Smoke-Test sind grün.
- Weitere Änderungen nur nach neuem Review-Auftrag.
- Bis dahin keine Logikänderungen mehr.

## Kurzform

- **Freeze aktiv.**
- **V3 freigegeben.**
- **Nächste Änderungen nur kontrolliert nach Review.**

## Eingefrorener Scope

- Präsenz-Penalty (`remote_first_hybrid_ok`: passed / penalty / failed / unclear)
- `presence_policy` in jeder `/fit-check`-Response
- Ausnahme-Schwelle: `min_score_for_auto_apply` = 90
- Boundary-Tests 1 / 2 / 3 / >3
- Smoke Grauzonen-JD (Trade-off)
- Ownership-Flags und Ranking-Band 12 (unverändert aus V2)

## Cursor-Regeln

- Aktiv: `.cursor/rules/v3-freeze.mdc`, `.cursor/rules/v3-policy.mdc`
- Historisch: V1/V2 Freeze-Hinweise

## Nächster Schritt

**V3 betriebsbereit** (A Doku sauber, B Smoke grün).  
Keine Kernlogik-Änderungen. Weiter nur Betrieb und echte Fälle — oder neuer Review-Auftrag.

**PM-Betriebsdoku:** [`FIT_LOGIC_NOTES.md`](FIT_LOGIC_NOTES.md) · Abschluss: [`DOCU_REVIEW.md`](DOCU_REVIEW.md)
