"""Text generation (Phase 2) – tailored CV & cover letters.

Entry points:
- selection_plan(...) – deterministic content selection (MVP)
- generate_cv_variant(...) – ATS-friendly markdown from SelectionPlan
- generate_cover_letter(...) – later
"""

from backend.generation.cv_variant import generate_cv_variant
from backend.generation.selection_plan import selection_plan

__all__ = ["selection_plan", "generate_cv_variant"]
