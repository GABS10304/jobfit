# Fit-Check – PM-Übersicht (V3 Freeze)

**Status:** V3 eingefroren. Diese Doku beschreibt den Ist-Zustand – keine neuen Regeln.

Operative Einstiege: `POST /fit-check` · SoT in `domain/` · Freeze: `docs/V3_FREEZE.md`

---

## 1. Pipeline (Reihenfolge)

```
JD-Text
  → Loader (SoT: constraints, role_fit_profile, cv_master)
  → Hard Constraints          ← können sofort no_go setzen
  → Ownership-Flag            ← proceed | verify_product_ownership | no_go
  → Role-Fit Scoring          ← außer bei Hard-no_go
  → Ranking (Tier-Band)
  → Filter in results / excluded_roles
  → Präsenz-Ausnahme (V3)     ← nur bei 2–3 Office-Tagen; kann results leeren; immer sichtbar
```

| Schritt | Was passiert | Blockiert Scoring? |
|---------|--------------|--------------------|
| Hard Gates | Sales, Work-Mode hart, Ownership fehlen | ja → `no_go`, leere `results` |
| Ownership unclear | Flag `verify_product_ownership` | nein – Scoring läuft |
| Ranking | Sortierung der Rollen | nein – ändert keine Flags |
| Review-Filter | Score-Schwelle → `results` vs. `excluded_roles` | nein |
| Präsenz 2–3 Tage | Penalty; Ausnahme nach Score; bei Deny → `no_go` | Scoring schon gelaufen; Deny leert `results` |

---

## 2. Wann welcher Fall?

| Fall | Wann | Scoring? | Typische PM-Lesart |
|------|------|----------|--------------------|
| **`no_go`** | Hard Gate fail (Sales, >3 Office-Tage, feste Präsenzpflicht, Work-Mode unklar, kein Ownership) **oder** Präsenz-Ausnahme verweigert (2–3 Tage, Score zu schwach) | nein / Scores nur in `excluded_roles` bei Ausnahme-Deny | Ablehnen oder manuell klären – System sagt Stopp |
| **`verify_product_ownership`** | Ownership in der JD unklar/implizit, sonst keine Hard-Blocks | ja | Interessant, aber Ownership vor Apply prüfen |
| **`proceed`** (normaler Run) | Hard Gates ok, Ownership klar; ggf. Präsenz-Ausnahme gewährt | ja | Freigabe für Review/Apply-Vorbereitung laut Process |

Zusätzlich immer: Bool `verify_product_ownership` (true nur im Verify-Fall).

---

## 3. Response-Felder (PM-Lesart)

| Feld | Bedeutung |
|------|-----------|
| `status_flag` | Gesamtentscheidung: `proceed` \| `verify_product_ownership` \| `no_go` |
| `verify_product_ownership` | true = Ownership unklar; Scoring trotzdem gelaufen |
| `presence_policy` | V3-Pflichtfeld: Präsenz-Level, Ausnahme ja/nein, Begründung (nie still) |
| `constraint_check` | Detail aller Hard/Soft-Checks + TODOs + `presence_requires_exception` |
| `results` | Rollen ≥ Review-Schwelle, gerankt – die „relevanten Treffer“ |
| `excluded_roles` | Gerankt, aber unter Review-Schwelle (Explainability); bei Ausnahme-Deny: alle Scores hier |
| `job_description_snippet` | Kurzausschnitt der JD |

**PM-Hinweis:** Bei Präsenz-Ausnahme verweigert wird `status_flag` auf `no_go` gesetzt, während `constraint_check.decision` noch `proceed` oder `verify_product_ownership` sein kann. Für die Gesamtentscheidung gilt immer **`status_flag`** (+ `presence_policy`).

`verify` + Präsenz-Ausnahme können zusammen vorkommen: Ownership unklar **und** 2–3 Tage mit starkem Fit → `status_flag=verify_product_ownership`, `presence_policy.exception_granted=true`.

### `constraint_check` kurz

- `decision` / `decision_reason` – Constraint-Entscheidung vor Ranking
- `hard_results` – je Constraint: `passed` \| `failed` \| `unclear` \| `penalty` \| `skipped`
- `soft_results` – Präferenzen, **blockieren nie**
- `presence_requires_exception` – true bei 2–3 Office-Tagen (Ausnahme steht in `presence_policy`)

---

## 4. Drei Ebenen – nicht vermischen

| Ebene | Job | Ändert `status_flag`? |
|-------|-----|------------------------|
| **Hard Gates** | Stoppen oder durchlassen (Sales, Work-Mode hart, Ownership fehlen) | ja → oft `no_go` |
| **Ownership-Verify** | Unklare Produktverantwortung markieren | ja → `verify_product_ownership`; Scoring weiter |
| **Ranking** | Bei ähnlichen Scores: Produkt > Koordination > Coaching (Band 12) | nein – nur Reihenfolge |

Ranking entscheidet **nicht**, ob ein Job erlaubt ist. Hard Gates und Präsenz-Ausnahme schon.

---

## 5. Präsenzlogik V3 (Kurzfassung)

Keine neuen Regeln – nur Ist-Zustand:

- **≤1 Office-Tag / remote-first** → normal erlaubt (`presence_policy.outcome = ok`)
- **2–3 Office-Tage** → Penalty; Ausnahme nur bei außergewöhnlich starker Rolle (bester Score ≥ Ausnahme-Schwelle aus SoT); immer in `presence_policy` sichtbar (`exception_granted` / `exception_denied`)
- **>3 Office-Tage oder feste Präsenzpflicht** → hartes `no_go`
- Work-Mode **unklar** → `no_go` (muss explizit sein)

Details: `docs/V3_RELEASE.md`, `docs/V3_FREEZE.md`

---

## 6. Hard Constraints (Überblick)

| ID | Kurz |
|----|------|
| `remote_first_hybrid_ok` | siehe §5 Präsenz |
| `no_hard_sales` | reines Hunter/Quota ohne Produkt → fail |
| `product_ownership_required` | klar → proceed-Pfad; unklar → verify; Anti-Cues → no_go |

Soft Constraints werden erklärt, fließen noch nicht in den Score.

---

## 7. Scoring & Ranking (Kurz)

- Score = Anteil gematchter Kernsignale (0–100), DE/EN-Synonyme
- `results`: Score ≥ Review-Schwelle aus SoT; sonst `excluded_roles`
- Ranking-Band: ähnliche Scores → Produktrollen vor Koordination vor Coaching

---

## 8. Referenz & Tests

| Fixture / Test | Kurz |
|----------------|------|
| `domain/fixtures/ref_smoke_pack_v3.yaml` | **Smoke-Referenzpaket (4 JDs)** – Stabilitätscheck, keine Logikänderung |
| `tests/test_smoke_ref_pack.py` | Erwartungswerte zum Referenzpaket |
| `docs/fixtures.md` | **Fixture-Liste** (Betriebsfälle, PM-Kurzform) |
| `domain/fixtures/README.md` | Fixture-Index inkl. Dateipfade |
| `domain/fixtures/ops_teamviewer_*.md` (+ `.yaml`) | Betriebsfall TeamViewer – verify, Hybrid ok, Scores = Shortlist |
| `domain/fixtures/ops_strong_product_more_presence.md` | Grauzone: starke Produktrolle + mehr Präsenz |
| `domain/fixtures/ops_coordination_with_product_share.md` | Grauzone: Koordination + Produktanteil |
| `domain/fixtures/ref_*` | ältere Einzel-Referenzfälle |
| `tests/test_v3_presence.py` | Präsenz Boundary + Smoke |
| `tests/test_v2_scenarios.py` / `test_reference_cases.py` | Ownership + Regression |
| `docs/SMOKE_TEST.md` | Grauzonen-Smoke Ownership |
| `docs/DOCU_REVIEW.md` | abgehaktes Doku-Review |

**Eine Zeile zum Referenzpaket:** Vier Referenz-JDs decken Produkt-Grauzone, starken Produktfit mit mehr Präsenz, koordinationslastigen Fall und Coaching-/Transformation-Fall ab; sie dienen nur als Stabilitätscheck ohne Logikänderung.


---

## 9. Bewusst noch nicht im Fit-Check

Compensation, Job-Types, Location jenseits Work-Mode, Soft-Gewichte im Score, CV-Overlap, Match-Patterns – siehe SoT/TODOs. Kein Auto-Apply, kein Scraping.

---

**Freeze / Betrieb:** V3 betriebsbereit (A+B abgeschlossen). Keine Kernlogik-Änderungen — nur Betrieb und echte Fälle, außer Bugfix oder neuer Review-Auftrag.
