# Sourcing Sprints (local learning log)

Kurze E2E-Läufe gegen echte Personio-Boards. Keine V3-Logik-Änderung; nur Beobachtungen zu Board-Auswahl, Prefilter und Pass-Raten (strong match: score ≥ 75).

Filter-Stack: Title-Prefilter → V3 fit-check → `domain/sourcing_filter.yaml` (pass / watchlist / reject).

CLI: `python scripts/fetch_jobs_batch.py --board-url <url> --include-weak-proceed --out …`

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

## Pass-Raten (kumuliert)

| Board | Discovered | Fit-checked | Passed | Pass-Rate (discovered) | Pass-Rate (fit-checked) |
|-------|------------|-------------|--------|------------------------|-------------------------|
| FLEX | 17 | 2 | 0 | 0% | 0% |
| credium | 2 | 1 | 0 | 0% | 0% |
| **Summe** | **19** | **3** | **0** | **0%** | **0%** |

## CLI-Lücke (notiert)

- `--cv-from-watchlist` vorhanden (Weak-Match-CVs).
- **`--cv-from-passed` fehlt** — Strong-Pass-CVs werden nicht auto-generiert. In Sprint 5 nicht gebraucht (0 passed); bei erstem Pass nachziehen.

## Nächster Sprint (Empfehlung)

1. **Mehr Boards parallel** (ePages, Mercanis, weitere DE/EU-SaaS) — Volumen statt Einzel-Board; Rate-Limit/Backoff einplanen.
2. **BA-API / Aggregator** prüfen — Personio-Einzelboards liefern zu wenig Product-Fit-Kandidaten für statistisch sinnvolle Pass-Raten.
3. **Allowlist feinjustieren** nur wenn Fake-Negatives klar sind — aktuell kommen AI-PM-Titel durch; Engpass ist **Score < 75**, nicht Title-Prefilter.
