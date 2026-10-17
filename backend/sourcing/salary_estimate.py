"""Salary forecast for a job: stated figure if the JD has one, else a band estimate.

Deterministic and explainable — every estimate lists the factors that produced
it (level, role, location, stage), so it can be challenged and tuned. Bands live
in ``domain/salary_bands.yaml``. Reporting layer only: it never gates a job and
never feeds V3 scoring.

Order:
1. JD states a figure (``salary_filter.extract_salary_range``) → basis "stated"
2. Otherwise level band (DE/CH) × role × location × stage → basis "estimated"
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from backend.sourcing.salary_filter import extract_salary_range

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BANDS_PATH = REPO_ROOT / "domain" / "salary_bands.yaml"
_WORD = "a-z0-9äöüß"
_YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:jahre|years|yrs|j\.)", re.IGNORECASE)
_LEVEL_ORDER = ["junior", "mid", "senior", "lead", "head", "cpo"]
_LEVEL_LABEL = {"junior": "Junior", "mid": "Mid", "senior": "Senior", "lead": "Lead/Principal",
                "head": "Head/Director", "cpo": "CPO/VP"}


@dataclass
class SalaryEstimate:
    low: int
    high: int
    currency: str
    basis: str  # "stated" | "estimated"
    confidence: str  # "hoch" | "mittel" | "niedrig"
    level: str | None = None
    region: str = "DE"
    factors: list[str] = field(default_factory=list)
    equity_note: bool = False
    below_minimum: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def label(self) -> str:
        unit = "k€" if self.currency == "EUR" else "k CHF"
        rng = (f"{self.low // 1000}" if self.low == self.high
               else f"{self.low // 1000}–{self.high // 1000}")
        how = "laut Anzeige" if self.basis == "stated" else "Prognose: " + " · ".join(self.factors)
        extra = " + Equity" if self.equity_note else ""
        warn = " ⚠️ unter deinem Minimum" if self.below_minimum else ""
        return f"{rng} {unit}{extra} ({how}){warn}"


@lru_cache(maxsize=4)
def load_bands(path: str | None = None) -> dict[str, Any]:
    return yaml.safe_load(Path(path or BANDS_PATH).read_text(encoding="utf-8")) or {}


def _hit(text: str, cues: list[str]) -> bool:
    for cue in cues:
        cue = str(cue).strip().casefold()
        if cue and re.search(rf"(?<![{_WORD}]){re.escape(cue)}(?![{_WORD}])", text):
            return True
    return False


def detect_region(text: str, bands: dict[str, Any]) -> str:
    for region, cues in (bands.get("region_cues") or {}).items():
        if _hit(text, cues):
            return region
    return "DE"


def detect_level(title: str, jd_text: str, bands: dict[str, Any]) -> tuple[str, list[str]]:
    title_cf = (title or "").casefold()
    notes: list[str] = []
    level = "mid"
    for candidate, cues in (bands.get("level_cues") or {}).items():
        if _hit(title_cf, cues):
            level = candidate
            break
    years = [int(m) for m in _YEARS_RE.findall(jd_text or "")]
    if years:
        max_years = max(years)
        for rule in bands.get("years_floor") or []:
            floor = rule["level"]
            if max_years >= int(rule["min_years"]) and _LEVEL_ORDER.index(floor) > _LEVEL_ORDER.index(level):
                notes.append(f"{max_years}+ Jahre gefordert")
                level = floor
                break
    return level, notes


def _first_multiplier(
    text: str, rules: list[dict[str, Any]], *, title: str = ""
) -> dict[str, Any] | None:
    for rule in rules or []:
        if _hit(title, rule.get("title_cues") or []) or _hit(text, rule.get("cues") or []):
            return rule
    return None


def _round_k(value: float) -> int:
    return int(round(value / 1000.0)) * 1000


def estimate_salary(
    *,
    title: str | None,
    jd_text: str | None,
    location: str | None = None,
    min_annual_base: float | None = None,
    bands: dict[str, Any] | None = None,
) -> SalaryEstimate:
    bands = bands or load_bands()
    full = " ".join(filter(None, [title, location, jd_text])).casefold()
    region = detect_region(" ".join(filter(None, [location, title, jd_text])).casefold(), bands)
    currency = (bands.get("currency_by_region") or {}).get(region, "EUR")

    stated = extract_salary_range(jd_text)
    if stated:
        low, high = int(stated[0]), int(stated[1])
        est = SalaryEstimate(low=low, high=high, currency=currency, basis="stated",
                             confidence="hoch", region=region, factors=["laut Anzeige"])
    else:
        level, level_notes = detect_level(title or "", jd_text or "", bands)
        low, high = (bands.get("levels") or {}).get(region, {}).get(level, [0, 0])
        factors = [_LEVEL_LABEL.get(level, level)] + level_notes
        factor = 1.0
        known = 1  # level always known (default mid)

        role = _first_multiplier(full, bands.get("role_multipliers"), title=(title or "").casefold())
        if role:
            factor *= float(role["factor"]); factors.append(role["label"])

        if region == "DE":
            # The job's own location field wins; the JD text (which often names
            # the HQ city of a remote role) is only a fallback.
            loc_text = (location or "").casefold().strip() or full
            loc = _first_multiplier(loc_text, bands.get("location_multipliers"))
            if loc:
                factor *= float(loc["factor"]); factors.append(loc["label"]); known += 1
        else:
            factors.append(region); known += 1

        stage = _first_multiplier(full, bands.get("stage_multipliers"))
        equity = False
        if stage:
            factor *= float(stage["factor"]); factors.append(stage["label"])
            equity = bool(stage.get("equity_note"))

        est = SalaryEstimate(
            low=_round_k(low * factor), high=_round_k(high * factor), currency=currency,
            basis="estimated", confidence="mittel" if known >= 2 else "niedrig",
            level=level, region=region, factors=factors, equity_note=equity,
        )

    if min_annual_base is not None and currency == "EUR":
        est.below_minimum = est.high < float(min_annual_base)
    return est
