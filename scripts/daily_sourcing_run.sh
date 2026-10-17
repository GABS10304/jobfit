#!/usr/bin/env bash
# Daily sourcing run — Personio + JOIN multi-board, no auto CV generation.
# Generation is now gated on explicit approval ("ja zu <job_id>" in chat),
# see scripts/prepare_application_draft.py + scripts/finalize_application.py.
#
# Intended launchd target (see scripts/install_daily_launchd.sh).
# Usage: ./scripts/daily_sourcing_run.sh [--with-workday] [--with-linkedin] [--with-decisions] [--no-join] [--no-ashby]
#
# JOIN (join.com) boards from domain/join_boards.yaml run by default — public
# company career pages, same posture as Personio. --no-join turns them off.
# Ashby boards from domain/ashby_boards.yaml also run by default (official
# public Job Posting API, one request per board). --no-ashby turns them off.
#
# --with-linkedin hits LinkedIn's public guest endpoints (personal-use only,
# see backend/sourcing/linkedin.py) — off by default, keep it that way unless
# you've deliberately decided the ToS tradeoff is fine for daily automation.
#
# --with-decisions runs the advocate/skeptic/decision agent (Claude API,
# real cost per job) on every new job found today — off by default until
# ANTHROPIC_API_KEY / `ant auth login` credentials are set up. Never sends
# anything; only decides whether drafting/outreach is worth the effort.

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

WITH_WORKDAY=0
WITH_LINKEDIN=0
WITH_DECISIONS=0
WITH_JOIN=1
WITH_ASHBY=1
for arg in "$@"; do
  case "$arg" in
    --with-workday) WITH_WORKDAY=1 ;;
    --with-linkedin) WITH_LINKEDIN=1 ;;
    --with-decisions) WITH_DECISIONS=1 ;;
    --no-join) WITH_JOIN=0 ;;
    --no-ashby) WITH_ASHBY=0 ;;
  esac
done

TOTAL_NEW=0
NEW_IDS_FILE="$OUT_DIR/new_job_ids_${STAMP}.json"
rm -f "$NEW_IDS_FILE"

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
  --out "$SHORTLIST" \
  --new-ids-out "$NEW_IDS_FILE")"
echo "$SUMMARY"
NEW_COUNT="$(echo "$SUMMARY" | grep -o 'NEW_COUNT=[0-9]*' | cut -d= -f2 || echo 0)"
TOTAL_NEW=$((TOTAL_NEW + NEW_COUNT))

if [[ "$WITH_JOIN" == "1" ]]; then
  JOIN_OUT="$OUT_DIR/join_${STAMP}.json"
  echo "== JOIN multi-board (startup career pages) =="
  if python scripts/fetch_jobs_multi_join.py \
      --out "$JOIN_OUT" \
      --delay 1.5 \
      --delay-between-boards 3.0; then
    JOIN_SHORTLIST="$OUT_DIR/shortlist_join_${STAMP}.md"
    JOIN_SUMMARY="$(python scripts/build_daily_shortlist.py \
      --artifact "$JOIN_OUT" \
      --run-date "$STAMP" \
      --out "$JOIN_SHORTLIST" \
      --new-ids-out "$NEW_IDS_FILE")"
    echo "$JOIN_SUMMARY"
    JOIN_NEW_COUNT="$(echo "$JOIN_SUMMARY" | grep -o 'NEW_COUNT=[0-9]*' | cut -d= -f2 || echo 0)"
    TOTAL_NEW=$((TOTAL_NEW + JOIN_NEW_COUNT))
  else
    echo "JOIN run failed — continuing with the other sources."
  fi
fi

if [[ "$WITH_ASHBY" == "1" ]]; then
  ASHBY_OUT="$OUT_DIR/ashby_${STAMP}.json"
  echo "== Ashby multi-board (official posting API) =="
  if python scripts/fetch_jobs_multi_ashby.py --out "$ASHBY_OUT"; then
    ASHBY_SHORTLIST="$OUT_DIR/shortlist_ashby_${STAMP}.md"
    ASHBY_SUMMARY="$(python scripts/build_daily_shortlist.py \
      --artifact "$ASHBY_OUT" \
      --run-date "$STAMP" \
      --out "$ASHBY_SHORTLIST" \
      --new-ids-out "$NEW_IDS_FILE")"
    echo "$ASHBY_SUMMARY"
    ASHBY_NEW_COUNT="$(echo "$ASHBY_SUMMARY" | grep -o 'NEW_COUNT=[0-9]*' | cut -d= -f2 || echo 0)"
    TOTAL_NEW=$((TOTAL_NEW + ASHBY_NEW_COUNT))
  else
    echo "Ashby run failed — continuing with the other sources."
  fi
fi

if [[ "$WITH_WORKDAY" == "1" ]]; then
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
    --out "$WORKDAY_SHORTLIST" \
    --new-ids-out "$NEW_IDS_FILE")"
  echo "$WORKDAY_SUMMARY"
  WORKDAY_NEW_COUNT="$(echo "$WORKDAY_SUMMARY" | grep -o 'NEW_COUNT=[0-9]*' | cut -d= -f2 || echo 0)"
  TOTAL_NEW=$((TOTAL_NEW + WORKDAY_NEW_COUNT))
fi

if [[ "$WITH_LINKEDIN" == "1" ]]; then
  LINKEDIN_OUT="$OUT_DIR/linkedin_${STAMP}.json"
  echo "== LinkedIn guest search (personal-use only, keep volume low) =="
  python scripts/fetch_jobs_multi_linkedin.py \
    --out "$LINKEDIN_OUT" \
    --limit-per-search 25 \
    --delay 2.0 \
    --delay-between-searches 5.0

  LINKEDIN_SHORTLIST="$OUT_DIR/shortlist_linkedin_${STAMP}.md"
  LINKEDIN_SUMMARY="$(python scripts/build_daily_shortlist.py \
    --artifact "$LINKEDIN_OUT" \
    --run-date "$STAMP" \
    --out "$LINKEDIN_SHORTLIST" \
    --new-ids-out "$NEW_IDS_FILE")"
  echo "$LINKEDIN_SUMMARY"
  LINKEDIN_NEW_COUNT="$(echo "$LINKEDIN_SUMMARY" | grep -o 'NEW_COUNT=[0-9]*' | cut -d= -f2 || echo 0)"
  TOTAL_NEW=$((TOTAL_NEW + LINKEDIN_NEW_COUNT))
fi

echo "Done. Total new proposals today: $TOTAL_NEW"

if [[ "$WITH_DECISIONS" == "1" && "$TOTAL_NEW" -gt 0 ]]; then
  echo "== Decision agent (advocate/skeptic/decision) on today's new jobs =="
  python scripts/run_decisions_for_new_jobs.py --job-ids-file "$NEW_IDS_FILE" || true
fi

if [[ "$TOTAL_NEW" -gt 0 ]]; then
  osascript -e "display notification \"$TOTAL_NEW neue Job-Vorschläge — im Chat ansehen\" with title \"Job Fit System\"" || true
fi
