"""Text generation (Phase 2) – tailored CV & cover letters.

Entry points:
- selection_plan(...) – deterministic content selection (MVP)
- generate_cv_variant(...) – later
- generate_cover_letter(...) – later
"""

from backend.generation.selection_plan import selection_plan

__all__ = ["selection_plan"]
