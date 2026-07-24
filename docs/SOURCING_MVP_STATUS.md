# Sourcing MVP Status

Kurzstatus der lokalen Pipeline (Personio → Fit → CV). Stand: Sprint 11.

## Pipeline

```
Board-Liste (personio_boards.yaml)
  → discover (Personio listings)
  → title prefilter (domain/sourcing_filter.yaml)
  → V3 fit-check (role_fit_profile + signal_lexicon)
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

## Bekannte Limits

- Nur Personio-Boards (kein LinkedIn/StepStone).
- Rate-Limits (429) → Boards werden übersprungen/retries; Delay nötig.
- Strong-Pass hängt stark am Lexikon + JD-Wording; kein Claim-Erfinden im CV.
- Prefilter verwirft viele Nicht-Product-Titel (hohe Reject-Rate, wenige Fit-Checks).
- Generated `out/` ist gitignored; Reviews liegen in Docs.
- Kein Auto-Apply, kein Tracking-UI in diesem MVP.

## Multi-Board ausführen

```bash
cd /path/to/job-fit-system
source .venv/bin/activate

# Alle Boards aus domain/personio_boards.yaml
python scripts/fetch_jobs_multi_board.py \
  --out /tmp/multi_board_e2e.json \
  --include-weak-proceed \
  --cv-from-passed \
  --cv-out-passed out/cv_passed

# Optional: weniger Jobs / Subset / langsameres Polling
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

## Aktueller Stand (Sprint 10/11)

- Multi-Board: 2 Strong-Passes (FLEX 76, credium 79).
- Passed-CVs reviewed; Renderer strippt Evidence-Tags (Sprint 11).
- Details: [`SOURCING_SPRINTS.md`](SOURCING_SPRINTS.md), [`CV_PASSED_REVIEW.md`](CV_PASSED_REVIEW.md).
