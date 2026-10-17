"""Remember which job detail pages were already fetched + fit-checked.

The state store (``jobs_state.json``) only keeps passed/watchlist rows, so a
rejected job used to be re-fetched every single day. That wastes the request
budget we deliberately keep small for public boards (LinkedIn especially).

This cache stores ``job_key -> last checked date`` for every detail fetch,
regardless of outcome, so the daily runners can skip anything checked within
the last ``ttl_days``. Spending fewer requests on known jobs is what lets the
runners look *wider* (more pages / queries) at the same traffic.

File: ``out/tracking/seen_jobs.json`` (gitignored with the rest of ``/out/``).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from backend.generation.watchlist_cv import job_id_from_url

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SEEN_PATH = REPO_ROOT / "out" / "tracking" / "seen_jobs.json"
DEFAULT_TTL_DAYS = 14


def job_key(url: str) -> str:
    """Numeric board id when parseable (stable across URL variants), else URL."""
    numeric = job_id_from_url(url)
    return numeric or url.split("?", 1)[0].rstrip("/")


class SeenCache:
    def __init__(self, path: Path | None = None, *, today: date | None = None) -> None:
        self.path = path or SEEN_PATH
        self.today = today or date.today()
        self._data: dict[str, str] = {}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8")) or {}
                if isinstance(raw, dict):
                    self._data = {str(k): str(v) for k, v in raw.items()}
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def is_fresh(self, url: str, ttl_days: int = DEFAULT_TTL_DAYS) -> bool:
        if ttl_days <= 0:
            return False
        stamp = self._data.get(job_key(url))
        if not stamp:
            return False
        try:
            seen = date.fromisoformat(stamp)
        except ValueError:
            return False
        return self.today - seen < timedelta(days=ttl_days)

    def mark(self, url: str) -> None:
        self._data[job_key(url)] = self.today.isoformat()

    def prune(self, max_age_days: int = 90) -> None:
        cutoff = self.today - timedelta(days=max_age_days)
        kept: dict[str, str] = {}
        for key, stamp in self._data.items():
            try:
                if date.fromisoformat(stamp) >= cutoff:
                    kept[key] = stamp
            except ValueError:
                continue
        self._data = kept

    def save(self) -> Path:
        self.prune()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return self.path

    def __len__(self) -> int:
        return len(self._data)
