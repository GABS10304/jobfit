"""Pydantic models for API request/response schemas and domain validation."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# --- API schemas ---


class FitCheckRequest(BaseModel):
    job_description: str = Field(..., min_length=1)
    role_ids: Optional[list[str]] = Field(
        default=None,
        description="Optional subset of role_ids from role_fit_profile.yaml. "
        "If omitted, all roles are scored.",
    )


class RoleFitResult(BaseModel):
    role_id: str
    role_name: str
    score: int = Field(..., ge=0, le=100)
    matched_signals: list[str]
    missing_signals: list[str]
    reason: str = ""
    passes_review_threshold: bool = False


class HardConstraintResult(BaseModel):
    id: str
    label: str
    status: Literal["passed", "failed", "unclear", "skipped", "penalty"]
    reason: str
    matched_cues: list[str] = Field(default_factory=list)


class SoftConstraintResult(BaseModel):
    id: str
    label: str
    weight: float
    status: Literal["matched", "not_matched", "skipped"]
    reason: str
    matched_cues: list[str] = Field(default_factory=list)


class PresencePolicyResult(BaseModel):
    """V3: Präsenz als Penalty / Ausnahme – immer explizit in der Response."""

    level: Literal[
        "remote_first_ok",
        "two_to_three_office_days",
        "hard_presence",
        "unclear",
    ]
    outcome: Literal[
        "ok",
        "penalty_pending",
        "exception_granted",
        "exception_denied",
        "no_go",
    ]
    reason: str
    exceptional_score_threshold: int = 90
    best_role_score: Optional[int] = None
    exception_granted: bool = False
    matched_cues: list[str] = Field(default_factory=list)


class ConstraintCheckResult(BaseModel):
    decision: Literal["proceed", "verify_product_ownership", "no_go"]
    decision_reason: str
    hard_results: list[HardConstraintResult]
    soft_results: list[SoftConstraintResult]
    todos: list[str] = Field(default_factory=list)
    verify_product_ownership: bool = Field(
        default=False,
        description="True when product ownership is unclear/implicit – scoring continues.",
    )
    presence_requires_exception: bool = False


class FitCheckResponse(BaseModel):
    job_description_snippet: str
    status_flag: Literal["proceed", "verify_product_ownership", "no_go"]
    verify_product_ownership: bool = False
    presence_policy: PresencePolicyResult
    constraint_check: ConstraintCheckResult
    results: list[RoleFitResult]
    excluded_roles: list[RoleFitResult] = Field(
        default_factory=list,
        description="Roles scored but below min_score_for_review (explainability).",
    )


class HealthResponse(BaseModel):
    status: str


# --- Domain schemas (YAML validation) ---


class EvidenceItem(BaseModel):
    project_name: str
    reason: str


class ExampleProject(BaseModel):
    project_name: str
    employer_or_client: str
    short_reason: str


class RoleSignals(BaseModel):
    role_id: str
    role_name: str
    priority: Optional[str] = None
    confidence_score: Optional[int] = Field(default=None, ge=0, le=100)
    summary: Optional[str] = None
    evidence_level: Optional[str] = None
    confidence_notes: Optional[str] = None
    core_signals_skills: list[str] = Field(default_factory=list)
    core_signals_domains: list[str] = Field(default_factory=list)
    core_signals_tools: list[str] = Field(default_factory=list)
    supporting_evidence: list[EvidenceItem] = Field(default_factory=list)
    example_projects: list[ExampleProject] = Field(default_factory=list)
    match_patterns_positive: list[str] = Field(default_factory=list)
    match_patterns_negative: list[str] = Field(default_factory=list)
    best_fit_contexts: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class RoleFitProfile(BaseModel):
    version: str = "0.1"
    roles: list[RoleSignals]


class Person(BaseModel):
    name: str
    location: Optional[str] = None
    languages: list[str] = Field(default_factory=list)
    profile_kernel: Optional[str] = None


class Employment(BaseModel):
    id: str
    company: str
    role_title: str
    start: str
    end: Optional[str] = None
    current: bool = False
    location: Optional[str] = None
    core_tasks: list[str] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)
    tools_methods: list[str] = Field(default_factory=list)
    relevance_note: Optional[str] = None
    evidence_strength: Optional[str] = None


class Project(BaseModel):
    id: str
    title: str
    context: Optional[str] = None
    role: Optional[str] = None
    problem: Optional[str] = None
    approach: Optional[str] = None
    result: Optional[str] = None
    supports_roles: list[str] = Field(default_factory=list)
    evidence_strength: Optional[str] = None


class Skill(BaseModel):
    id: str
    name: str
    evidence: Optional[str] = None
    strength: Optional[str] = None


class CvMaster(BaseModel):
    person: Person
    employments: list[Employment] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    open_todos: list[str] = Field(default_factory=list)


class HardConstraint(BaseModel):
    id: str
    label: str
    enabled: bool = True
    notes: Optional[str] = None


class SoftConstraint(BaseModel):
    id: str
    label: str
    weight: float = 1.0


class LocationPreferences(BaseModel):
    preferred_locations: list[str] = Field(default_factory=list)
    avoid_locations: list[str] = Field(default_factory=list)
    travel_tolerance: Optional[str] = None


class Compensation(BaseModel):
    currency: Optional[str] = None
    min_annual_base: Optional[float] = None
    target_annual_base: Optional[float] = None
    notes: Optional[str] = None


class JobTypes(BaseModel):
    preferred: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)


class ApplicationRules(BaseModel):
    min_score_for_review: int = 75
    min_score_for_assisted_apply: int = 80
    min_score_for_auto_apply: int = 90
    require_manual_approval_for_submit: bool = True
    auto_apply_enabled: bool = False


class Constraints(BaseModel):
    hard_constraints: list[HardConstraint] = Field(default_factory=list)
    soft_constraints: list[SoftConstraint] = Field(default_factory=list)
    location_preferences: Optional[LocationPreferences] = None
    compensation: Optional[Compensation] = None
    job_types: Optional[JobTypes] = None
    application_rules: ApplicationRules = Field(default_factory=ApplicationRules)
    notes: list[str] = Field(default_factory=list)


# --- CV tailoring (Phase 2) ---


class CvRulesLanguage(BaseModel):
    default: str = "de"
    note: Optional[str] = None


class CvRulesLimits(BaseModel):
    max_bullets_per_employment: int = 5
    max_bullets_per_project: int = 3
    max_total_pages_hint: int = 2
    max_employments: int = 4
    max_projects: int = 4


class CvRulesEvidence(BaseModel):
    min_strength_for_inclusion: Literal["strong", "medium", "weak"] = "medium"
    exclude_markers: list[str] = Field(default_factory=lambda: ["[TODO]"])
    never_promote_todo_to_claim: bool = True
    note: Optional[str] = None


class CvRulesKeywordMirroring(BaseModel):
    source: str = "cv_master_only"
    no_invention: bool = True
    note: Optional[str] = None


class CvRules(BaseModel):
    version: str = "0.1"
    language: CvRulesLanguage = Field(default_factory=CvRulesLanguage)
    limits: CvRulesLimits = Field(default_factory=CvRulesLimits)
    section_order: list[str] = Field(default_factory=list)
    evidence: CvRulesEvidence = Field(default_factory=CvRulesEvidence)
    keyword_mirroring: CvRulesKeywordMirroring = Field(
        default_factory=CvRulesKeywordMirroring
    )


class SelectedBullet(BaseModel):
    source_type: Literal["employment", "project"]
    source_id: str
    bullet_text: str
    evidence_strength: Optional[str] = None
    jd_keyword_overlap: list[str] = Field(default_factory=list)
    rank_score: float = 0.0
    rationale: str = ""


class SelectedEmployment(BaseModel):
    employment_id: str
    bullets: list[SelectedBullet] = Field(default_factory=list)
    rationale: str = ""


class SelectedProject(BaseModel):
    project_id: str
    rank_score: float = 0.0
    matched_signals: list[str] = Field(default_factory=list)
    bullets: list[SelectedBullet] = Field(default_factory=list)
    rationale: str = ""


class SelectionPlan(BaseModel):
    selected_role_id: str
    selected_role_name: str
    role_source: Literal["results", "excluded_roles"]
    role_score: int = Field(..., ge=0, le=100)
    matched_signals: list[str] = Field(default_factory=list)
    selected_employment_ids: list[str] = Field(default_factory=list)
    selected_project_ids: list[str] = Field(default_factory=list)
    employments: list[SelectedEmployment] = Field(default_factory=list)
    projects: list[SelectedProject] = Field(default_factory=list)
    rationale: str = ""
    explain: dict[str, str] = Field(default_factory=dict)


class CvVariant(BaseModel):
    """Tailored CV variant – MVP wraps deterministic selection plan."""

    selection_plan: SelectionPlan
    language: str = "de"
    section_order: list[str] = Field(default_factory=list)
    max_pages_hint: int = 2
