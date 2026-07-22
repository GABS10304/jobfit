"""Job sourcing (Phase 3) – scraper / API clients."""

from backend.sourcing.personio import NormalizedJobDescription, fetch_personio_job

__all__ = ["NormalizedJobDescription", "fetch_personio_job"]
