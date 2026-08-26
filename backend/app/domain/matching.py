from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.profile import EvidenceReference


class StrictMatchModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RequirementImportance(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"


class MatchCategory(StrEnum):
    EDUCATION = "education"
    SKILLS = "skills"
    EXPERIENCE = "experience"
    LOCATION = "location"
    INDUSTRY = "industry"


class RequirementStatus(StrEnum):
    MET = "met"
    MISSING = "missing"


class JobRequirement(StrictMatchModel):
    requirement_id: UUID
    text: str = Field(min_length=1, max_length=300)
    importance: RequirementImportance
    category: MatchCategory
    standard_key: str = Field(min_length=1, max_length=100)
    ordinal: int = Field(ge=1)


class CandidateEvidence(StrictMatchModel):
    evidence_id: UUID
    category: MatchCategory
    standard_key: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=500)
    references: list[EvidenceReference] = Field(min_length=1, max_length=3)


class RequirementMatch(StrictMatchModel):
    requirement_id: UUID
    text: str
    importance: RequirementImportance
    category: MatchCategory
    standard_key: str
    ordinal: int = Field(ge=1)
    status: RequirementStatus
    evidence: list[CandidateEvidence]
    explanation: str
    action: str | None


class CategoryCoverage(StrictMatchModel):
    category: MatchCategory
    weight_percent: int = Field(ge=0, le=100)
    coverage_percent: int = Field(ge=0, le=100)
    met: int = Field(ge=0)
    missing: int = Field(ge=0)


class JobMatch(StrictMatchModel):
    match_result_id: UUID
    job_id: UUID
    title: str
    company: str
    summary: str
    required_coverage_points: int = Field(ge=0)
    required_coverage_max: int = Field(ge=0)
    preferred_coverage_points: int = Field(ge=0)
    preferred_coverage_max: int = Field(ge=0)
    required_rank_score: int = Field(ge=0, le=10_000)
    preferred_rank_score: int = Field(ge=0, le=10_000)
    category_coverage: list[CategoryCoverage]
    requirements: list[RequirementMatch]


class MatchResults(StrictMatchModel):
    analysis_id: UUID
    profile_id: UUID
    matcher_version: str
    job_requirements_version: str
    top_matches: list[JobMatch] = Field(min_length=3, max_length=3)
