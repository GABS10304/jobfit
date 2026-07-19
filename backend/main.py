"""Job Fit System API – Phase 1: Constraints → Role-Fit → /fit-check."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from backend import data_loader, fit_engine
from backend.models import FitCheckRequest, FitCheckResponse, HealthResponse

app = FastAPI(
    title="Job Fit System",
    description=(
        "Lokales Job-Matching: Hard Constraints → Role-Fit-Scoring → erklärbare Results. "
        "Source of Truth: domain/cv_master.yaml|json, role_fit_profile.yaml, constraints.yaml."
    ),
    version="0.1.0",
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/fit-check", response_model=FitCheckResponse)
def fit_check(body: FitCheckRequest) -> FitCheckResponse:
    try:
        profile = data_loader.get_role_fit_profile()
        constraints = data_loader.get_constraints()
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

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
