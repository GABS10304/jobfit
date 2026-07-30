"""Per-user profile store. Default user `gabriel` maps to domain/ SoT."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from backend import data_loader
from backend.models import (
    Constraints,
    CreateProfileRequest,
    RoleFitProfile,
    UserProfile,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = REPO_ROOT / "profiles"
DEFAULT_USER_ID = "gabriel"

_USER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _profile_dir(user_id: str) -> Path:
    return PROFILES_DIR / user_id


def _profile_path(user_id: str) -> Path:
    return _profile_dir(user_id) / "profile.yaml"


def validate_user_id(user_id: str) -> str:
    if not _USER_ID_RE.match(user_id):
        raise ValueError(
            f"Invalid user_id {user_id!r}. Use lowercase letters, digits, _ or -."
        )
    return user_id


def load_gabriel_profile() -> UserProfile:
    """Built-in default: existing domain YAML files."""
    return UserProfile(
        user_id=DEFAULT_USER_ID,
        display_name="Gabriel",
        profile_version="domain",
        role_fit_profile=data_loader.load_role_fit_profile(),
        constraints=data_loader.load_constraints(),
        cv_master=data_loader.load_cv_master(),
    )


def empty_profile(user_id: str, display_name: str = "") -> UserProfile:
    return UserProfile(
        user_id=user_id,
        display_name=display_name or user_id,
        profile_version="0.1",
        role_fit_profile=RoleFitProfile(version="0.1", roles=[]),
        constraints=Constraints(),
        cv_master=None,
    )


def load_user_profile(user_id: str) -> UserProfile:
    user_id = validate_user_id(user_id)
    if user_id == DEFAULT_USER_ID:
        return load_gabriel_profile()
    path = _profile_path(user_id)
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {user_id}")
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Profile must be a mapping: {path}")
    raw.setdefault("user_id", user_id)
    return UserProfile.model_validate(raw)


def save_user_profile(profile: UserProfile) -> UserProfile:
    user_id = validate_user_id(profile.user_id)
    if user_id == DEFAULT_USER_ID:
        raise ValueError(
            "Cannot overwrite built-in user 'gabriel' via profile store. "
            "Edit domain/*.yaml instead."
        )
    path = _profile_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = profile.model_dump(mode="json", exclude_none=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False)
    return profile


def create_user_profile(req: CreateProfileRequest) -> UserProfile:
    user_id = validate_user_id(req.user_id)
    if user_id == DEFAULT_USER_ID:
        raise ValueError("user_id 'gabriel' is reserved for domain SoT")
    if _profile_path(user_id).exists():
        raise FileExistsError(f"Profile already exists: {user_id}")
    profile = empty_profile(user_id, req.display_name)
    return save_user_profile(profile)


def list_user_ids() -> list[str]:
    ids = [DEFAULT_USER_ID]
    if PROFILES_DIR.exists():
        for child in sorted(PROFILES_DIR.iterdir()):
            if child.is_dir() and _profile_path(child.name).exists():
                if child.name != DEFAULT_USER_ID:
                    ids.append(child.name)
    return ids


def save_cv_draft(user_id: str, markdown: str) -> Path:
    """Persist Master-CV-style draft next to profile.yaml."""
    user_id = validate_user_id(user_id)
    if user_id == DEFAULT_USER_ID:
        raise ValueError("Cannot write cv_draft for built-in user 'gabriel'")
    path = _profile_dir(user_id) / "cv_draft.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path


def upsert_user_profile(profile: UserProfile) -> UserProfile:
    """Create or overwrite a non-gabriel profile."""
    return save_user_profile(profile)


def resolve_fit_check_inputs(
    user_id: str | None,
) -> tuple[UserProfile, RoleFitProfile, Constraints]:
    """Load profile slices for fit-check. user_id omitted → domain SoT (gabriel)."""
    if user_id is None:
        user = load_gabriel_profile()
    else:
        user = load_user_profile(user_id)
    return user, user.role_fit_profile, user.constraints
