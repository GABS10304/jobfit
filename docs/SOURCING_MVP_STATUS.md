# Sourcing MVP Status

Kurzstatus der lokalen Pipeline (Personio → Fit → CV). Stand: Sprint 14.

## Ergebnis (aktuell)

Multi-Board **kann Strong Passes** erzeugen (Score ≥ 75, Schwelle unverändert):

| Board | Rolle | Score | Status |
|-------|-------|------:|--------|
| FLEX | AI Product Manager | **76** | passed |
| credium | AI Produkt Manager (SaaS) | **79** | passed |

Passed-CVs: `out/cv_passed/` (gitignored). Review: [`CV_PASSED_REVIEW.md`](CV_PASSED_REVIEW.md).

**Option A′** (optional Tools im Score): umgesetzt und aktiv; Tools erhöhen den Nenner nur wenn gematcht. Details: [`REVIEW_AUFTRAG_TOOL_SIGNALS.md`](REVIEW_AUFTRAG_TOOL_SIGNALS.md). Keine V3-Threshold-Änderung.

## Pipeline

```
Board-Liste (personio_boards.yaml)
  → discover (Personio listings)
    → title prefilter (domain/sourcing_filter.yaml)
    → V3 fit-check (role_fit_profile + signal_lexicon; Option A′ optional tools)
    → label: passed (≥75) | watchlist (weak proceed) | reject
    → optional: selection_plan + CV-Render → out/cv_passed | out/cv_watchlist
```

| Stufe | Was passiert | Output |
|-------|--------------|--------|
| Scraper | Personio Board + Job-HTML → normalisierte JD | `job.jd_text`, URL, Titel |
| Filter | Title-Prefilter; Product-Role-Gate | candidates / rejects |
| Fit-Check | Deterministische V3-Scores pro Zielrolle | top_score, role_id, matched_signals |
| Passed / Watchlist | Score ≥ 75 → passed; schwache Product-Hits → watchlist | JSON + optional Markdown-CVs |
| CV | `selection_plan` + `generate_cv_variant` (kein LLM) | ATS-Markdown DE |

## End-to-End ausführen

```bash
cd /path/to/job-fit-system
source .venv/bin/activate

# Alle Boards aus domain/personio_boards.yaml → Fit + Passed-CVs
python scripts/fetch_jobs_multi_board.py \
  --out /tmp/multi_board_e2e.json \
  --include-weak-proceed \
  --cv-from-passed \
  --cv-out-passed out/cv_passed

# Subset (schnell, rate-limit-schonend)
python scripts/fetch_jobs_multi_board.py \
  --board-ids flex credium \
  --limit-per-board 5 \
  --delay 2.5 \
  --backoff 8 \
  --out /tmp/multi_board_subset.json \
  --cv-from-passed
```

Single-Board: `python scripts/fetch_jobs_batch.py --board-url <url> --include-weak-proceed --out …`

Watchlist-CVs nachträglich: `python scripts/run_watchlist_cv.py --from-json <batch.json>`

## Bekannte Limits

- Personio-Boards + Workday Einzel-JD-Fetch (kein LinkedIn/StepStone; kein Workday Board-Discovery noch).
- Rate-Limits (429) → Boards werden übersprungen/retries; Delay nötig.
- Strong-Pass hängt am Lexikon + JD-Wording; kein Claim-Erfinden im CV.
- Prefilter verwirft viele Nicht-Product-Titel (hohe Reject-Rate, wenige Fit-Checks).
- Generated `out/` ist gitignored; Reviews liegen in Docs.
- Kein Auto-Apply, kein Tracking-UI in diesem MVP.

## Sprint-Pfad (kurz)

| Sprint | Ergebnis |
|--------|----------|
| 9 | Option A′ → credium **79**, FLEX noch Watchlist (65) |
| 10 | Lexikon-Gap FLEX → **76** + **79**; erste Strong-Passes |
| 11 | Passed-CV Review; Renderer strippt Evidence-Tags |
| 13 | Role-aware Employment-Ranking (Scrum-Master nur bei Coach-JD) |
| 14 | Status-Docs finalisiert; Repo remote |
| 19 | Workday JD-Fetcher MVP; ING Live = `verify` / Filter-Reject (Score 36) |

Details: [`SOURCING_SPRINTS.md`](SOURCING_SPRINTS.md), [`SCORE_DIAGNOSIS_AI_PM.md`](SCORE_DIAGNOSIS_AI_PM.md).
