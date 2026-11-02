"""
Core Pydantic data schemas for the Job Hunter system.
Strictly candidate-agnostic, versioned, and cleanly split between LLM schemas and system schemas.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SeniorityLevel(str, Enum):
    INTERN = "Intern"
    JUNIOR = "Junior"
    MID = "Mid"
    SENIOR = "Senior"
    STAFF = "Staff"
    PRINCIPAL = "Principal"
    MANAGER = "Manager"


class WorkMode(str, Enum):
    REMOTE = "Remote"
    HYBRID = "Hybrid"
    ONSITE = "On-site"
    UNKNOWN = "Unknown"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class CVExtraction(BaseModel):
    """Schema returned by the LLM during Intake / CV Extraction."""
    name: Optional[str] = Field(default=None, description="Full candidate name if explicitly stated")
    current_location: Optional[str] = Field(default=None, description="Current residence/location")
    languages: List[str] = Field(default_factory=list, description="Natural languages spoken")
    years_experience: Optional[float] = Field(default=None, description="Computed total years of professional experience")
    seniority: SeniorityLevel = Field(default=SeniorityLevel.MID, description="Assessed overall seniority level")
    primary_domain: str = Field(..., description="Primary engineering domain")
    target_roles: List[str] = Field(default_factory=list, description="4-8 targeted job titles demonstrated in CV")
    must_have_skills: List[str] = Field(default_factory=list, description="Hands-on skills proven across roles")
    nice_to_have_skills: List[str] = Field(default_factory=list, description="Secondary or adjacent skills")
    tools: List[str] = Field(default_factory=list, description="EDA tools, lab instruments, software platforms")
    education: List[str] = Field(default_factory=list, description="Degrees and institutions")
    certifications: List[str] = Field(default_factory=list, description="Professional certifications")
    industries_worked_in: List[str] = Field(default_factory=list, description="Sectors demonstrated in CV")
    clarifying_questions: List[str] = Field(
        default_factory=list,
        description="3 critical questions only on things the CV cannot answer (visa status, target countries, etc.)"
    )


class UserProfile(BaseModel):
    """Complete Candidate Profile used at system runtime."""
    model_config = ConfigDict(extra="allow")

    name: str = Field(description="Candidate name")
    current_location: str = Field(description="Candidate current location")
    primary_domain: str = Field(description="Primary technical domain")
    target_roles: List[str] = Field(description="Specific target titles")
    seniority_levels: List[SeniorityLevel] = Field(
        default_factory=lambda: [SeniorityLevel.MID, SeniorityLevel.SENIOR],
        description="Seniority levels to match"
    )
    target_countries: List[str] = Field(description="Allowed countries for matching")
    target_industries: List[str] = Field(default_factory=list, description="Target sectors")
    must_have_skills: List[str] = Field(description="Mandatory skills")
    nice_to_have_skills: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    work_modes: List[str] = Field(
        default_factory=lambda: ["On-site", "Hybrid", "Remote"],
        description="Preferred work arrangements: On-site, Hybrid, Remote"
    )
    needs_visa_sponsorship: bool = Field(
        default=True,
        description="Whether the candidate needs visa sponsorship to work in target countries"
    )
    include_internships: bool = Field(
        default=False,
        description="Whether to match intern or working student postings"
    )
    include_graduate_programs: bool = Field(
        default=False,
        description="Whether to match graduate schemes / traineeships"
    )
    is_deep_scale: bool = Field(
        default=True,
        description="Whether to run deep/massive directory scout"
    )
    scale_option: str = Field(
        default="2",
        description="Target volume option selected by candidate: 1, 2, or 3"
    )
    summary: str = Field(default="", description="Executive summary")
    clarifications_needed: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("seniority_levels", mode="before")
    @classmethod
    def normalize_seniority_levels(cls, v: Any) -> List[SeniorityLevel]:
        if not v:
            return [SeniorityLevel.MID, SeniorityLevel.SENIOR]
        if isinstance(v, (str, SeniorityLevel)):
            v = [v]
        mapping = {
            "intern": SeniorityLevel.INTERN,
            "internship": SeniorityLevel.INTERN,
            "graduate": SeniorityLevel.INTERN,
            "trainee": SeniorityLevel.INTERN,
            "junior": SeniorityLevel.JUNIOR,
            "entry": SeniorityLevel.JUNIOR,
            "entry-level": SeniorityLevel.JUNIOR,
            "associate": SeniorityLevel.JUNIOR,
            "mid": SeniorityLevel.MID,
            "mid-level": SeniorityLevel.MID,
            "midlevel": SeniorityLevel.MID,
            "engineer": SeniorityLevel.MID,
            "experienced": SeniorityLevel.MID,
            "senior": SeniorityLevel.SENIOR,
            "sr": SeniorityLevel.SENIOR,
            "lead": SeniorityLevel.SENIOR,
            "staff": SeniorityLevel.STAFF,
            "principal": SeniorityLevel.PRINCIPAL,
            "manager": SeniorityLevel.MANAGER,
            "director": SeniorityLevel.MANAGER,
        }
        result = []
        for item in v:
            if isinstance(item, SeniorityLevel):
                result.append(item)
            elif isinstance(item, str):
                normalized = item.strip().lower()
                if normalized in mapping:
                    result.append(mapping[normalized])
                else:
                    matched = False
                    for enum_val in SeniorityLevel:
                        if enum_val.value.lower() == normalized:
                            result.append(enum_val)
                            matched = True
                            break
                    if not matched:
                        result.append(SeniorityLevel.MID)
        return result or [SeniorityLevel.MID]


class JobClassification(BaseModel):
    """Structured output returned by the Job Classifier Agent."""
    eligible: bool = Field(default=True, description="False if any hard filter is violated")
    eligibility_reason: Optional[str] = Field(default=None, description="Detailed reason if eligible=False")
    work_mode: str = Field(..., description="Must be 'Remote', 'Hybrid', 'On-site', or 'Unknown'")
    work_mode_reason: str = Field(..., description="Rationale for work arrangement classification")
    match_score: int = Field(..., ge=0, le=100, description="Fit score 0-100")
    match_reason: str = Field(..., description="Technical engineering rationale")
    evidence_quote: Optional[str] = Field(default=None, description="Verbatim sentence from job posting")
    is_relevant: bool = Field(default=False, description="True if score >= MIN_RELEVANCE_SCORE")
    visa_sponsorship: str = Field(default="unknown", description="'yes', 'no', or 'unknown'")
    clearance_or_citizenship_required: bool = Field(default=False, description="Whether citizenship/clearance/ITAR required")
    visa_evidence_quote: Optional[str] = Field(default=None, description="Verbatim quote regarding visa/citizenship")
    country: Optional[str] = Field(default=None, description="Resolved job country")
    city: Optional[str] = Field(default=None, description="Resolved job city")
    seniority: Optional[str] = Field(default=None, description="Seniority level of the role")
    required_skills: List[str] = Field(default_factory=list, description="Skills extracted from posting")
    posted_date: Optional[str] = Field(default=None, description="Date posted if present")
    injection_suspected: bool = Field(default=False, description="True if prompt injection attempts detected")


class VerificationResult(BaseModel):
    """Structured audit verdict from the Independent Adversarial Verifier."""
    is_verified: bool = Field(..., description="Whether approved for verified output")
    confidence_score: int = Field(..., ge=0, le=100, description="Verification confidence")
    audit_notes: str = Field(..., description="Truthful verdict label and audit notes")
    verifier_engine: str = Field(default="RULE_BASED", description="LLM_APPROVED or FALLBACK_RULES_APPROVED")
    still_open: bool = Field(default=True, description="Whether job is verified still open")
    quote_verified: bool = Field(default=False, description="Whether quote is an exact substring of page")
    flags: List[str] = Field(default_factory=list, description="Audit anomaly flags")


class Company(BaseModel):
    id: Optional[int] = None
    name: str
    domain: str
    country: str
    industry: str
    careers_url: Optional[str] = None
    ats_detected: Optional[str] = None
    slug: Optional[str] = None
    relevance_score: int = 0
    jobs_seen: int = 0
    status: str = "active"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class JobPosting(BaseModel):
    id: Optional[int] = None
    company_id: int
    company_name: str
    title: str
    job_url: str
    canonical_key: Optional[str] = None
    location: str
    country: str
    work_mode: str = "On-site"
    match_score: int
    match_reason: str
    evidence_quote: Optional[str] = None
    source_url: str
    seniority: Optional[str] = None
    visa_sponsorship: str = "unknown"
    clearance_or_citizenship_required: bool = False
    visa_evidence_quote: Optional[str] = None
    eligible: bool = True
    eligibility_reason: Optional[str] = None
    still_open: bool = True
    verified: bool = False
    verification_notes: Optional[str] = None
    classifier_engine: Optional[str] = None
    classifier_model: Optional[str] = None
    prompt_version: Optional[str] = None
    verifier_engine: Optional[str] = None
    checked_at: datetime = Field(default_factory=datetime.utcnow)
