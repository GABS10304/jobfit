"""Job Fit System API – Phase 1: Constraints → Role-Fit → /fit-check.

Onboarding/completeness is additive and does not change V3 fit logic.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend import completeness, cv_bootstrap, cv_ingest, data_loader, fit_engine, profile_store
from backend.models import (
    Constraints,
    CreateProfileRequest,
    CvUploadResponse,
    DomainSettingsUpdate,
    FitCheckRequest,
    FitCheckResponse,
    HealthResponse,
    ProfileCompletenessResponse,
    UserProfile,
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="Job Fit System",
    description=(
        "Lokales Job-Matching: Hard Constraints → Role-Fit-Scoring → erklärbare Results. "
        "Source of Truth: domain/cv_master.yaml|json, role_fit_profile.yaml, constraints.yaml. "
        "Multi-User-Onboarding: /profiles + /onboarding (CV-Drop + Completeness %)."
    ),
    version="0.1.0",
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/fit-check", response_model=FitCheckResponse)
def fit_check(body: FitCheckRequest) -> FitCheckResponse:
    try:
        user, profile, constraints = profile_store.resolve_fit_check_inputs(body.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if body.user_id is not None and body.user_id != profile_store.DEFAULT_USER_ID:
        snap = completeness.compute_completeness(user)
        if not snap.fit_check_unlocked:
            raise HTTPException(
                status_code=403,
                detail={
                    "message": "Profil noch nicht fit-ready.",
                    "fit_ready_pct": snap.fit_ready_pct,
                    "missing_required": snap.missing_required,
                },
            )

    if body.role_ids:
        known = {r.role_id for r in profile.roles}
        unknown = [rid for rid in body.role_ids if rid not in known]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown role_ids: {unknown}. Known: {sorted(known)}",
            )

    return fit_engine.run_fit_check(
        job_description=body.job_description,
        profile=profile,
        constraints=constraints,
        role_ids=body.role_ids,
    )


@app.get("/onboarding")
def onboarding_page() -> FileResponse:
    path = STATIC_DIR / "onboarding.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="onboarding.html missing")
    return FileResponse(path)


@app.get("/settings")
def settings_page() -> FileResponse:
    path = STATIC_DIR / "settings.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="settings.html missing")
    return FileResponse(path)


@app.get("/domain/settings", response_model=Constraints)
def get_domain_settings() -> Constraints:
    """Gehalt/Ausschluss/Impact – gabriel's own domain SoT (constraints.yaml)."""
    return data_loader.load_constraints()


@app.put("/domain/settings", response_model=Constraints)
def put_domain_settings(body: DomainSettingsUpdate) -> Constraints:
    """Read-modify-write into domain/constraints.yaml; leaves hard/soft constraints intact."""
    return data_loader.update_constraints_settings(body)


@app.post("/onboarding/cv-upload", response_model=CvUploadResponse)
async def cv_upload(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    display_name: str = Form(""),
) -> CvUploadResponse:
    try:
        profile_store.validate_user_id(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if user_id == profile_store.DEFAULT_USER_ID:
        raise HTTPException(
            status_code=400,
            detail="user_id 'gabriel' ist Domain-SoT – bitte andere ID wählen.",
        )

    raw = await file.read()
    try:
        text = cv_ingest.extract_text(file.filename, raw)
    except cv_ingest.CvIngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        result = cv_bootstrap.bootstrap_from_text(
            text,
            user_id=user_id,
            display_name=display_name,
            source_filename=file.filename,
        )
        profile_store.upsert_user_profile(result.profile)
        profile_store.save_cv_draft(user_id, result.cv_draft_md)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    snap = completeness.compute_completeness(result.profile)
    return CvUploadResponse(
        user_id=result.profile.user_id,
        display_name=result.profile.display_name,
        profile=result.profile,
        completeness=snap,
        cv_draft_md=result.cv_draft_md,
        matched_signal_ids=result.matched_signal_ids,
        suggested_role_id=result.suggested_role_id,
        notes=result.notes,
    )


@app.get("/profiles", response_model=list[str])
def list_profiles() -> list[str]:
    return profile_store.list_user_ids()


@app.post("/profiles", response_model=UserProfile, status_code=201)
def create_profile(body: CreateProfileRequest) -> UserProfile:
    try:
        return profile_store.create_user_profile(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/profiles/{user_id}", response_model=UserProfile)
def get_profile(user_id: str) -> UserProfile:
    try:
        return profile_store.load_user_profile(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/profiles/{user_id}", response_model=UserProfile)
def put_profile(user_id: str, body: UserProfile) -> UserProfile:
    if body.user_id != user_id:
        raise HTTPException(status_code=400, detail="user_id in path and body must match")
    try:
        return profile_store.save_user_profile(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/profiles/{user_id}/completeness", response_model=ProfileCompletenessResponse)
def get_completeness(user_id: str) -> ProfileCompletenessResponse:
    try:
        profile = profile_store.load_user_profile(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    snap = completeness.compute_completeness(profile)
    return ProfileCompletenessResponse(
        user_id=profile.user_id,
        display_name=profile.display_name,
        completeness=snap,
    )
