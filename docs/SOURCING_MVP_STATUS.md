# Sourcing MVP Status

Kurzstatus der lokalen Pipeline (Personio → Fit → CV; Workday optional). Stand: Sprint A–C (2026-07-25).

## Ergebnis (aktuell)

Multi-Board **kann Strong Passes** erzeugen (Score ≥ 75, Schwelle unverändert):

| Board | Rolle | Score | Status |
|-------|-------|------:|--------|
| FLEX | AI Product Manager | **76** | passed |
| credium | AI Produkt Manager (SaaS) | **79** | passed |
| conceptboard | Senior Product Manager | **93** | passed (KEEP, siehe Review) |

Passed-CVs: `out/cv_passed/` (gitignored). Reviews: [`CV_PASSED_REVIEW.md`](CV_PASSED_REVIEW.md), [`CONCEPTBOARD_PASS_REVIEW.md`](CONCEPTBOARD_PASS_REVIEW.md).

**Option A′** (optional Tools im Score): aktiv. Keine V3-Threshold-Änderung.

## Pipeline

```
Board-Liste (personio_boards.yaml | workday_boards.yaml)
  → discover (Personio HTML | Workday CXS)
    → location prefilter (Workday, optional DE/Remote keywords)
    → title prefilter (domain/sourcing_filter.yaml)
    → V3 fit-check (role_fit_profile + signal_lexicon; Option A′ optional tools)
    → label: passed (≥75) | watchlist (weak proceed) | reject
    → optional: selection_plan + CV-Render → out/cv_passed | out/cv_watchlist
```

## Weekly Run (empfohlen)

```bash
cd /path/to/job-fit-system
source .venv/bin/activate

# Personio alle Boards → Fit + Passed-CVs
./scripts/weekly_sourcing_run.sh

# Optional zusätzlich Workday (YAML location_keywords)
./scripts/weekly_sourcing_run.sh --with-workday
```

Ergebnis-JSON unter `out/weekly/`; CVs unter `out/cv_passed/`.

## End-to-End (manuell)

```bash
# Personio subset
python scripts/fetch_jobs_multi_board.py \
  --board-ids flex credium conceptboard \
  --out /tmp/multi_board_subset.json \
  --include-weak-proceed \
  --cv-from-passed

# Workday mit DE/Remote-Keywords aus YAML
python scripts/fetch_jobs_multi_workday.py \
  --board-ids salesforce \
  --limit-per-board 5 \
  --out /tmp/multi_workday.json
```

## Bekannte Limits

- Personio-Boards + Workday Multi-Board (CXS); ING Workday oft WAF → disabled.
- Workday `Remote` matcht auch US-Remote — ggf. Keywords ohne nacktes Remote nutzen.
- Title-Prefilter lässt „Product Marketing“ teils durch (Watchlist, selten Strong Pass).
- Kein Auto-Apply, kein LinkedIn/StepStone.

Details: [`SOURCING_SPRINTS.md`](SOURCING_SPRINTS.md).
