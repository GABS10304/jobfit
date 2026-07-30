#!/usr/bin/env bash
# Daily sourcing run — Personio multi-board, no auto CV generation.
# Generation is now gated on explicit approval ("ja zu <job_id>" in chat),
# see scripts/prepare_application_draft.py + scripts/finalize_application.py.
#
# Intended launchd target (see scripts/install_daily_launchd.sh).
# Usage: ./scripts/daily_sourcing_run.sh [--with-workday]

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAMP="$(date -u +%Y%m%d)"
OUT_DIR="${OUT_DIR:-$ROOT/out/daily}"
mkdir -p "$OUT_DIR"

if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

TOTAL_NEW=0

PERSONIO_OUT="$OUT_DIR/personio_${STAMP}.json"
echo "== Personio multi-board (daily, no auto-CV) =="
python scripts/fetch_jobs_multi_board.py \
  --out "$PERSONIO_OUT" \
  --include-weak-proceed \
  --delay 2.5 \
  --backoff 8

SHORTLIST="$OUT_DIR/shortlist_${STAMP}.md"
SUMMARY="$(python scripts/build_daily_shortlist.py \
  --artifact "$PERSONIO_OUT" \
  --run-date "$STAMP" \
  --out "$SHORTLIST")"
echo "$SUMMARY"
NEW_COUNT="$(echo "$SUMMARY" | grep -o 'NEW_COUNT=[0-9]*' | cut -d= -f2 || echo 0)"
TOTAL_NEW=$((TOTAL_NEW + NEW_COUNT))

if [[ "${1:-}" == "--with-workday" ]]; then
  WORKDAY_OUT="$OUT_DIR/workday_${STAMP}.json"
  echo "== Workday multi-board (DE/Remote location keywords from YAML) =="
  python scripts/fetch_jobs_multi_workday.py \
    --out "$WORKDAY_OUT" \
    --limit-per-board 5 \
    --include-weak-proceed \
    --delay 2.0 \
    --backoff 8

  WORKDAY_SHORTLIST="$OUT_DIR/shortlist_workday_${STAMP}.md"
  WORKDAY_SUMMARY="$(python scripts/build_daily_shortlist.py \
    --artifact "$WORKDAY_OUT" \
    --run-date "$STAMP" \
    --out "$WORKDAY_SHORTLIST")"
  echo "$WORKDAY_SUMMARY"
  WORKDAY_NEW_COUNT="$(echo "$WORKDAY_SUMMARY" | grep -o 'NEW_COUNT=[0-9]*' | cut -d= -f2 || echo 0)"
  TOTAL_NEW=$((TOTAL_NEW + WORKDAY_NEW_COUNT))
fi

echo "Done. Total new proposals today: $TOTAL_NEW"

if [[ "$TOTAL_NEW" -gt 0 ]]; then
  osascript -e "display notification \"$TOTAL_NEW neue Job-Vorschläge — im Chat ansehen\" with title \"Job Fit System\"" || true
fi
