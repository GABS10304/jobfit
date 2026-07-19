# V3 Review – Präsenz-Penalty

**Status: FREEZE AKTIV – V3 freigegeben**  
**Tests:** 51 passed (2026-07-19)  
**Logik:** eingefroren – keine Änderungen ohne neuen Review-Auftrag

## Reihenfolge (erledigt)

1. Präsenzregel v3 implementiert  
2. Boundary-Tests 1 / 2 / 3 / >3  
3. Ausnahme-Begründung in `presence_policy` abgesichert  
4. Smoke mit realer Grauzonen-JD  
5. Review + Freeze

## Grenzen (kein stilles Verschieben)

| Grenze | Verhalten | Sichtbarkeit |
|--------|-----------|--------------|
| ≤1 Office-Tag | `passed` / `outcome=ok` | normal erlaubt |
| 2–3 Office-Tage, Score < 90 | `penalty` → `exception_denied` → `no_go` | `reason` mit Score + Schwelle |
| 2–3 Office-Tage, Score ≥ 90 | `penalty` → `exception_granted` | `exception_granted=true` + Begründung |
| >3 Office-Tage | `failed` / `hard_presence` | hartes No-Go, kein Scoring |
| Feste Präsenzpflicht | hartes No-Go | auch bei starkem Fit |

Schwelle für Top-Rollen-Ausnahme: `application_rules.min_score_for_auto_apply` = **90**.

## Ziele – Check

- [x] Kein stilles Verschieben von Grenzfällen (`presence_policy` Pflichtfeld)
- [x] Flexible Top-Rollen möglich (Ausnahme bei Score ≥ 90)
- [x] Normale Präsenzpflicht klar begrenzt (>3 / feste Pflicht = No-Go)

## Smoke (Grauzone)

JD mit 2 Office-Tagen als Trade-off, explizit *keine* feste Präsenzpflicht → Penalty + sichtbare `exception_granted` bei starkem Produktfit.

## Freeze

Siehe `docs/V3_FREEZE.md`. **Nächste Änderungen nur kontrolliert nach Review.**
