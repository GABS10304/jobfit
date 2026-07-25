#!/usr/bin/env bash
# Weekly sourcing run — Personio multi-board (+ optional Workday EU filter).
# Usage:
#   ./scripts/weekly_sourcing_run.sh
#   ./scripts/weekly_sourcing_run.sh --with-workday

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAMP="$(date -u +%Y%m%d)"
OUT_DIR="${OUT_DIR:-$ROOT/out/weekly}"
mkdir -p "$OUT_DIR"

if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi

PERSONIO_OUT="$OUT_DIR/personio_${STAMP}.json"
echo "== Personio multi-board =="
python scripts/fetch_jobs_multi_board.py \
  --out "$PERSONIO_OUT" \
  --include-weak-proceed \
  --cv-from-passed \
  --cv-out-passed "$ROOT/out/cv_passed" \
  --delay 2.5 \
  --backoff 8

echo "Personio results: $PERSONIO_OUT"

if [[ "${1:-}" == "--with-workday" ]]; then
  WORKDAY_OUT="$OUT_DIR/workday_${STAMP}.json"
  echo "== Workday multi-board (DE/Remote location keywords from YAML) =="
  python scripts/fetch_jobs_multi_workday.py \
    --out "$WORKDAY_OUT" \
    --limit-per-board 5 \
    --include-weak-proceed \
    --delay 2.0 \
    --backoff 8
  echo "Workday results: $WORKDAY_OUT"
fi

echo "Done. Passed CVs under out/cv_passed/ (gitignored)."
