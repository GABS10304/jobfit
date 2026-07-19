"""Load and validate domain Source-of-Truth files (YAML / JSON)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import yaml

from backend.models import Constraints, CvMaster, RoleFitProfile

REPO_ROOT = Path(__file__).resolve().parent.parent
DOMAIN_DIR = REPO_ROOT / "domain"


def _ensure_mapping(data: object, path: Path) -> dict:
    if data is None:
        raise ValueError(f"Domain file is empty: {path}")
    if not isinstance(data, dict):
        raise ValueError(f"Domain file must be a mapping/object: {path}")
    return data


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Domain file not found: {path}")
    with path.open(encoding="utf-8") as f:
        return _ensure_mapping(yaml.safe_load(f), path)


def _read_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Domain file not found: {path}")
    with path.open(encoding="utf-8") as f:
        return _ensure_mapping(json.load(f), path)


def _read_domain_file(path: Path) -> dict:
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        return _read_yaml(path)
    if suffix == ".json":
        return _read_json(path)
    raise ValueError(f"Unsupported domain file type: {path}")


def load_cv_master(path: Path | None = None) -> CvMaster:
    """Load Master-CV. Default SSOT: domain/cv_master.yaml."""
    raw = _read_domain_file(path or DOMAIN_DIR / "cv_master.yaml")
    return CvMaster.model_validate(raw)


def load_cv_master_json(path: Path | None = None) -> CvMaster:
    """Load Master-CV JSON mirror (must stay in sync with YAML)."""
    raw = _read_json(path or DOMAIN_DIR / "cv_master.json")
    return CvMaster.model_validate(raw)


def assert_cv_master_parity() -> None:
    """Fail if YAML and JSON Master-CV diverge (SSOT integrity)."""
    yaml_raw = _read_yaml(DOMAIN_DIR / "cv_master.yaml")
    json_raw = _read_json(DOMAIN_DIR / "cv_master.json")
    if yaml_raw != json_raw:
        raise ValueError(
            "SSOT mismatch: domain/cv_master.yaml and domain/cv_master.json differ. "
            "Edit both or sync from the canonical YAML."
        )


def load_role_fit_profile(path: Path | None = None) -> RoleFitProfile:
    raw = _read_domain_file(path or DOMAIN_DIR / "role_fit_profile.yaml")
    return RoleFitProfile.model_validate(raw)


def load_constraints(path: Path | None = None) -> Constraints:
    raw = _read_domain_file(path or DOMAIN_DIR / "constraints.yaml")
    return Constraints.model_validate(raw)


@lru_cache(maxsize=1)
def get_role_fit_profile() -> RoleFitProfile:
    """Cached profile for API requests. Call clear_domain_cache() after edits."""
    return load_role_fit_profile()


@lru_cache(maxsize=1)
def get_cv_master() -> CvMaster:
    return load_cv_master()


@lru_cache(maxsize=1)
def get_constraints() -> Constraints:
    return load_constraints()


def clear_domain_cache() -> None:
    get_role_fit_profile.cache_clear()
    get_cv_master.cache_clear()
    get_constraints.cache_clear()
