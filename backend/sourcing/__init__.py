"""Job sourcing (Phase 3) – scraper / API clients."""

from backend.sourcing.personio import (
    JobListing,
    NormalizedJobDescription,
    discover_job_listings,
    discover_job_urls,
    fetch_personio_job,
)
from backend.sourcing.workday import (
    discover_job_listings as discover_workday_job_listings,
    discover_job_urls as discover_workday_job_urls,
    fetch_workday_job,
    is_workday_board_url,
    is_workday_job_url,
)

__all__ = [
    "JobListing",
    "NormalizedJobDescription",
    "discover_job_listings",
    "discover_job_urls",
    "discover_workday_job_listings",
    "discover_workday_job_urls",
    "fetch_personio_job",
    "fetch_workday_job",
    "is_workday_board_url",
    "is_workday_job_url",
]
