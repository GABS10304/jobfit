# V3 Release Notes

**Status: FREEZE AKTIV – freigegeben**  
**Datum:** 2026-07-19

## Was ändert sich

Präsenz ist keine binäre Soft-OK mehr, sondern eine **Penalty-Policy** mit expliziter Ausnahme.

| Level | Cue (Beispiele) | Outcome |
|-------|-----------------|---------|
| `remote_first_ok` | remote / hybrid / ≤1 Office-Tag | `ok` – normal erlaubt |
| `two_to_three_office_days` | 2–3 Präsenztage | Penalty → Scoring → Ausnahme nur wenn `best_role_score ≥ min_score_for_auto_apply` (90) |
| `hard_presence` | >3 Tage, Präsenzpflicht, überwiegend vor Ort | `no_go` – hart |
| `unclear` | kein Work-Mode-Hinweis | `no_go` (unverändert) |

Die Ausnahme darf **nie stillschweigend** passieren: Feld `presence_policy` in jeder `/fit-check`-Response.

## Response-Erweiterung

```json
"presence_policy": {
  "level": "two_to_three_office_days",
  "outcome": "exception_granted",
  "reason": "...",
  "exceptional_score_threshold": 90,
  "best_role_score": 95,
  "exception_granted": true,
  "matched_cues": ["2 präsenztage"]
}
```

`outcome`-Werte: `ok` | `penalty_pending` | `exception_granted` | `exception_denied` | `no_go`

Bei `exception_denied`: `status_flag=no_go`, `results=[]`, Scores in `excluded_roles` (Explainability).

## SoT

`domain/constraints.yaml` – Notes und `min_score_for_auto_apply: 90` als Ausnahme-Schwelle.

## Tests

- `tests/test_v3_presence.py`
  - Boundary Constraint-Layer: 1 / 2 / 3 / >3 Office-Tage
  - Boundary Fit-Check: 1 ok; 2 weak deny; 2–3 strong grant; >3 / Pflicht no_go
  - Smoke Grauzone: Trade-off-JD (2 Tage, keine feste Präsenzpflicht) → explizite Ausnahme
- Smoke/Reference/V2-Regression unverändert grün

## Nicht geändert

- Ownership-Flags, Ranking-Band 12, Soft-Cue-Hygiene (V2)
- Kein Auto-Apply, kein Scraping

## Freeze

**Freeze aktiv. V3 freigegeben.** Siehe `docs/V3_FREEZE.md` und `.cursor/rules/v3-freeze.mdc`.  
Keine Regeländerung ohne neuen Review-Auftrag + Tests.
