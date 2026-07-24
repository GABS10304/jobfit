# Sourcing Sprints (local learning log)

Kurze E2E-Läufe gegen echte Personio-Boards. Keine V3-Logik-Änderung; nur Beobachtungen zu Board-Auswahl, Prefilter und Pass-Raten (strong match: score ≥ 75).

Filter-Stack: Title-Prefilter → V3 fit-check → `domain/sourcing_filter.yaml` (pass / watchlist / reject).

CLI (single board): `python scripts/fetch_jobs_batch.py --board-url <url> --include-weak-proceed --out …`

CLI (multi-board): `python scripts/fetch_jobs_multi_board.py --out …`  
Boards: `domain/personio_boards.yaml`. `--include-weak-proceed` default **on**; optional `--limit-per-board N`, `--delay`, `--backoff`. Dead/429 boards werden übersprungen.

## Sprint 4 — FLEX (Baseline)

| Feld | Wert |
|------|------|
| Board | `https://flex-capital-management-gmbh.jobs.personio.de/` |
| Discovered | 17 |
| Prefilter rejects | 15 |
| Fit-checked | 2 |
| Passed (≥75) | **0** |
| Watchlist | 1 |
| Rejected | 16 |

Lesart: Portfolio-Board mit wenigen Product-Titeln; Prefilter verwirft den Großteil. Ein schwacher Product-Kandidat landet auf Watchlist, kein Strong-Pass.

## Sprint 5 — credium (zweites Board, AI/PM-lastig)

| Feld | Wert |
|------|------|
| Board | `https://credium.jobs.personio.de/?language=de` |
| Auswahlgrund | Verifizierter AI-/Produkt-Manager-Posting (DE SaaS); `discover_job_urls` > 0 |
| Discovered | 2 |
| Prefilter rejects | 1 (`Initiativbewerbung`) |
| Fit-checked | 1 |
| Passed (≥75) | **0** |
| Watchlist | 1 |
| Rejected | 1 |
| Artifact | `/tmp/board2_e2e.json` |

Watchlist-Detail:

- **AI Produkt Manager:in (m/w/d) – Gebäudemodernisierung Wohngebäude (SaaS)**  
  `verify_product_ownership`, top_score **38**, role `ai_product_manager` → watchlist (`weak_score=38<75`)

Lesart: Thematisch passender Titel kommt durch Prefilter und Product-Role-Gate, bleibt aber klar unter der Strong-Match-Bar (75). Board-Qualität (AI-PM) allein erzeugt keinen Pass.

### Probe vor Auswahl (nicht voller E2E)

Kurz geprüft, dass Boards laden und Listings liefern (Stand Sprint 5):

| Board | Listings | Product-ish Titel (Stichprobe) |
|-------|----------|--------------------------------|
| epages-gmbh | 3 | Product Manager – E-Commerce Plattform |
| mercanis | 16 | Product Success Manager |
| certivity | 3 | (keine Product-Titel in Discovery) |
| ocumeda-ag | 9 | (keine Product-Titel in Discovery) |

Weitere URL-Probes teils mit Personio **429** abgebrochen — bei Batch-Läufen Rate-Limits beachten.

## Sprint 6 — Multi-board batch

| Feld | Wert |
|------|------|
| Boards-Datei | `domain/personio_boards.yaml` (7 Boards) |
| Runner | `scripts/fetch_jobs_multi_board.py` |
| Flags | `--include-weak-proceed` default on; delay 2.5s |
| Artifact | `/tmp/multi_board_e2e.json` |
| Boards ok / error / skipped | **7 / 0 / 0** |
| Discovered | **54** |
| Prefilter rejects | 49 |
| Fit-checked | **5** |
| Passed (≥75) | **0** |
| Watchlist | **2** |
| Rejected | 52 |

Pro Board:

| Board | Discovered | Fit-checked | Passed | Watchlist | Rejected |
|-------|------------|-------------|--------|-----------|----------|
| flex | 17 | 2 | 0 | 1 | 16 |
| credium | 2 | 1 | 0 | 1 | 1 |
| epages | 3 | 1 | 0 | 0 | 3 |
| mercanis | 16 | 1 | 0 | 0 | 16 |
| certivity | 3 | 0 | 0 | 0 | 3 |
| ocumeda | 9 | 0 | 0 | 0 | 9 |
| getsafe | 4 | 0 | 0 | 0 | 4 |

Watchlist (overall):

- flex — **AI Product Manager (m/w/d)** — `proceed`, score **32**, role `technical_product_manager`
- credium — **AI Produkt Manager:in … (SaaS)** — `verify_product_ownership`, score **38**, role `ai_product_manager`

Weitere Fit-Checks ohne Watchlist (no_go / nicht watchlist-fähig):

- epages — Product Manager – E-Commerce Plattform → `no_go`
- mercanis — Product Success Manager → `no_go`
- flex — Omikron Product Manager Electronic Banking → `no_go`

Lesart: Mehr Volumen (54 Listings / 5 Fit-Checks) bestätigt Sprint-5-Befund — **kein Strong-Pass**. Watchlist bleibt primärer Output. Engpass weiterhin Score 32–38 ≪ 75 bei echten AI-PM-Titeln; zusätzliche Boards ohne Product-Titel erhöhen nur Prefilter-Rejects.

## Pass-Raten (kumuliert, Stand Sprint 6)

| Board | Discovered | Fit-checked | Passed | Watchlist | Pass-Rate (fit-checked) |
|-------|------------|-------------|--------|-----------|-------------------------|
| flex | 17 | 2 | 0 | 1 | 0% |
| credium | 2 | 1 | 0 | 1 | 0% |
| epages | 3 | 1 | 0 | 0 | 0% |
| mercanis | 16 | 1 | 0 | 0 | 0% |
| certivity | 3 | 0 | 0 | 0 | — |
| ocumeda | 9 | 0 | 0 | 0 | — |
| getsafe | 4 | 0 | 0 | 0 | — |
| **Summe** | **54** | **5** | **0** | **2** | **0%** |

## Sprint 7–9 (Score-Pfad, Kurz)

- Sprint 7: Lexikon-Synonyme → FLEX/credium AI-PM Top **46** (weiter ≪ 75).
- Sprint 9: Option A′ (Tools optional) → **credium 79** (Pass), **FLEX 65** (Watchlist). Schwelle unverändert 75.
- Details: [`SCORE_DIAGNOSIS_AI_PM.md`](SCORE_DIAGNOSIS_AI_PM.md), [`REVIEW_AUFTRAG_TOOL_SIGNALS.md`](REVIEW_AUFTRAG_TOOL_SIGNALS.md).

## Sprint 10 — FLEX Lexikon-Gap + Multi-Board Pass

| Feld | Wert |
|------|------|
| Fokus | FLEX required-signal Gap 65→≥75 (nur Lexikon-Synonyme; keine Threshold-/CV-Erfindung) |
| Lexikon | `evals`→`data_driven_decision_making`; PE/Mittelstand/`portcos`→`b2b_saas` |
| Remeasure | FLEX AI-PM **76** (Pass); credium AI-PM **79** (unverändert Pass) |
| Runner | `scripts/fetch_jobs_multi_board.py --include-weak-proceed --cv-from-passed` |
| Artifact | `/tmp/multi_board_sprint10.json` |
| Boards ok / error / skipped | **7 / 0 / 0** |
| Discovered | **54** |
| Fit-checked | **5** |
| Passed (≥75) | **2** |
| Watchlist | **0** |
| Rejected | **52** |

Passed:

- flex — **AI Product Manager (m/w/d)** — `proceed`, score **76**, role `ai_product_manager`
- credium — **AI Produkt Manager:in … (SaaS)** — `verify_product_ownership`, score **79**, role `ai_product_manager`

CV-Pfade (`out/cv_passed/`, gitignored):

- `passed_score76_2689046_ai-product-manager-m-w-d.md`
- `passed_score79_2286082_ai-produkt-manager-in-m-w-d-geb-udemodernisierun.md`

CLI: `--cv-from-passed` / `--cv-out-passed` in Batch + Multi-Board ergänzt.

Lesart: Erste Strong-Passes auf Multi-Board. FLEX schließt Domain/Skill-Gap über JD-nahe Synonyme; `product_analytics` / `privacy` / `govtech` / `regulated` bleiben auf FLEX unmatched (kein JD-Wording).

## Pass-Raten (kumuliert, Stand Sprint 10 Multi-Board)

| Board | Discovered | Fit-checked | Passed | Watchlist | Pass-Rate (fit-checked) |
|-------|------------|-------------|--------|-----------|-------------------------|
| flex | 17 | 2 | 1 | 0 | 50% |
| credium | 2 | 1 | 1 | 0 | 100% |
| epages | 3 | 1 | 0 | 0 | 0% |
| mercanis | 16 | 1 | 0 | 0 | 0% |
| certivity | 3 | 0 | 0 | 0 | — |
| ocumeda | 9 | 0 | 0 | 0 | — |
| getsafe | 4 | 0 | 0 | 0 | — |
| **Summe** | **54** | **5** | **2** | **0** | **40%** |

## Sprint 11 — Passed-CV Quality Review

| Feld | Wert |
|------|------|
| Fokus | ATS-Review der 2 Passed-CVs; Renderer/Rules-Fixes ohne Master-CV-Rewrite |
| Fixes | Provenance-Tags strippen; Meta-Bullets (`CV-Varianten`/`Original-CV`) exclude; Profil-Kapitalisierung |
| Docs | [`CV_PASSED_REVIEW.md`](CV_PASSED_REVIEW.md), [`SOURCING_MVP_STATUS.md`](SOURCING_MVP_STATUS.md) |
| CVs | `out/cv_passed/` regeneriert (gitignored) |

Lesart: Checks überwiegend pass; Restpunkte sind Master-Wording, Zertifikatslänge und Project-Problem-Fragmente — nicht Score-/Lexikon-Themen.

## Sprint 17 — Board-Expansion + Remeasure

| Feld | Wert |
|------|------|
| Fokus | +9 verifizierte Personio-Boards (DE/EU product/tech); Multi-Board Remeasure |
| Boards-Datei | `domain/personio_boards.yaml` (**16** aktiv; `disabled: true` wird von `load_boards` übersprungen) |
| Runner | `scripts/fetch_jobs_multi_board.py --include-weak-proceed --cv-from-passed --delay 3.0 --backoff 10` |
| Artifact | `/tmp/multi_board_sprint17.json` |
| Boards ok / error / skipped | **16 / 0 / 0** |
| Discovered | **155** |
| Fit-checked | **16** |
| Passed (≥75) | **3** |
| Watchlist | **1** |
| Rejected | **151** |

Neu in YAML (Probe `discover_job_urls` / listings > 0):

| id | Board | Listings (Probe) | Product-ish (Stichprobe) |
|----|-------|------------------|--------------------------|
| conceptboard | Conceptboard | 9 | Senior Product Manager; Product Analytics Manager |
| sipgate | sipgate | 8 | mehrere Produktmanagement-Titel inkl. AI & Flow |
| cloover | Cloover | 14 | Senior Product Manager |
| chrono24 | Chrono24 | 20 | (Director of Product auf Site; Lauf: 0 Fit-Checks) |
| metro-markets | METRO Markets | 3 | (Lauf: keine Product-Titel in Discovery) |
| pitch | Pitch | 10 | tech openings |
| codecentric | codecentric | 22 | consultancy/tech volume |
| finanztip | Finanztip | 12 | false-positive „Production“ → no_go |
| clark | CLARK | 3 | few listings |

Passed:

- flex — **AI Product Manager (m/w/d)** — `proceed`, score **76**, role `ai_product_manager`
- credium — **AI Produkt Manager:in … (SaaS)** — `verify_product_ownership`, score **79**, role `ai_product_manager`
- conceptboard — **Senior Product Manager (m/w/d)** — `proceed`, score **93**, role `ai_product_manager` *(neu)*

Watchlist:

- conceptboard — **Product Analytics Manager - Customer Retention & Expansion (m/w/d)** — score **57**, role `ai_product_manager`

CV-Pfade (`out/cv_passed/`, gitignored) — neu:

- `passed_score93_2544351_senior-product-manager-m-w-d.md` (+ `.txt` / `.pdf`)

Unverändert regeneriert: score76 FLEX, score79 credium (jeweils `.md` / `.txt` / `.pdf`).

Lesart: Board-Volume 54→155, Fit-Checks 5→16, Strong-Passes 2→**3**. Neuer Pass kommt von Conceptboard (Senior PM, 93). sipgate/cloover liefern Fit-Checks ohne Pass/Watchlist; mehrere Volume-Boards erhöhen nur Prefilter-Rejects. Keine Scoring-/Schwellen-Änderung.

## Pass-Raten (kumuliert, Stand Sprint 17 Multi-Board)

| Board | Discovered | Fit-checked | Passed | Watchlist | Pass-Rate (fit-checked) |
|-------|------------|-------------|--------|-----------|-------------------------|
| flex | 17 | 2 | 1 | 0 | 50% |
| credium | 2 | 1 | 1 | 0 | 100% |
| epages | 3 | 1 | 0 | 0 | 0% |
| mercanis | 16 | 1 | 0 | 0 | 0% |
| certivity | 3 | 0 | 0 | 0 | — |
| ocumeda | 9 | 0 | 0 | 0 | — |
| getsafe | 4 | 0 | 0 | 0 | — |
| conceptboard | 9 | 2 | 1 | 1 | 50% |
| sipgate | 8 | 5 | 0 | 0 | 0% |
| cloover | 14 | 3 | 0 | 0 | 0% |
| chrono24 | 20 | 0 | 0 | 0 | — |
| metro-markets | 3 | 0 | 0 | 0 | — |
| pitch | 10 | 0 | 0 | 0 | — |
| codecentric | 22 | 0 | 0 | 0 | — |
| finanztip | 12 | 1 | 0 | 0 | 0% |
| clark | 3 | 0 | 0 | 0 | — |
| **Summe** | **155** | **16** | **3** | **1** | **19%** |

## Nächster Sprint (Empfehlung)

1. Conceptboard-Pass (93) + Analytics-Watchlist (57) gegen Lexikon/JD prüfen — ohne Threshold zu senken.
2. sipgate Produktmanagement-Titel: warum kein Pass/Watchlist (Role-Gate vs. Score).
3. Master-Bullets Meta-/Proof-Wording bereinigen (SSOT); Volume-Boards ohne Product-Titel nur bei Bedarf behalten.
