"""Job sourcing (Phase 3) – scraper / API clients."""

from backend.sourcing.personio import (
    JobListing,
    NormalizedJobDescription,
    discover_job_listings,
    discover_job_urls,
    fetch_personio_job,
)

__all__ = [
    "JobListing",
    "NormalizedJobDescription",
    "discover_job_listings",
    "discover_job_urls",
    "fetch_personio_job",
]
