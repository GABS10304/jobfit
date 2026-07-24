"""Text generation (Phase 2) – tailored CV & cover letters.

Entry points:
- selection_plan(...) – deterministic content selection (MVP)
- generate_cv_variant(...) – ATS-friendly markdown from SelectionPlan
- watchlist_cv helpers – weak-match CV render from sourcing watchlist
- generate_cover_letter(...) – later
"""

from backend.generation.cv_variant import generate_cv_variant
from backend.generation.selection_plan import selection_plan
from backend.generation.watchlist_cv import (
    render_watchlist_cv,
    write_watchlist_cv_from_row,
    write_watchlist_cvs,
)

__all__ = [
    "selection_plan",
    "generate_cv_variant",
    "render_watchlist_cv",
    "write_watchlist_cv_from_row",
    "write_watchlist_cvs",
]
