"""Job sourcing (Phase 3) – scraper / API clients."""

from backend.sourcing.personio import (
    NormalizedJobDescription,
    discover_job_urls,
    fetch_personio_job,
)

__all__ = ["NormalizedJobDescription", "discover_job_urls", "fetch_personio_job"]
