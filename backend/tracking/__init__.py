"""Application tracking (Phase 4+).

state_store.py: cross-run job dedup + approval status (new -> proposed ->
approved -> draft_ready -> finalized). Used by scripts/daily_sourcing_run.sh,
scripts/prepare_application_draft.py and scripts/finalize_application.py.
"""
