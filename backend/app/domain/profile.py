import re
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PartialDate = Annotated[str, Field(pattern=r"^\d{4}(?:-(?:0[1-9]|1[0-2]))?$")]


class StrictProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class QualificationKind(StrEnum):
    CERTIFICATION = "certification"
    LICENCE = "licence"
    PROFESSIONAL = "professional_qualification"
    VOCATIONAL = "vocational_training"
    OTHER = "other"


class EducationLevel(StrEnum):
    SECONDARY = "secondary"
    VOCATIONAL = "vocational"
    BACHELORS = "bachelors"
    MASTERS = "masters"
    DOCTORATE = "doctorate"

    @property
    def eqf_level(self) -> int:
        return {
            EducationLevel.SECONDARY: 4,
            EducationLevel.VOCATIONAL: 5,
            EducationLevel.BACHELORS: 6,
            EducationLevel.MASTERS: 7,
            EducationLevel.DOCTORATE: 8,
        }[self]

    @property
    def display_name(self) -> str:
        return {
            EducationLevel.SECONDARY: "Secondary education",
            EducationLevel.VOCATIONAL: "Vocational qualification",
            EducationLevel.BACHELORS: "Bachelor's degree",
            EducationLevel.MASTERS: "Master's degree",
            EducationLevel.DOCTORATE: "Doctorate",
        }[self]


class SkillSource(StrEnum):
    ESCO = "esco"
    ONET = "onet"
    JOB_MATCHER_EXTENSION = "job_matcher_extension"


class SkillMappingMethod(StrEnum):
    EXACT_ALIAS = "exact_alias"
    VECTOR = "vector"


class EvidenceReference(StrictProfileModel):
    block_id: UUID
    quote: str = Field(min_length=3, max_length=500)


class EvidenceBackedStatement(StrictProfileModel):
    text: str = Field(min_length=1, max_length=500)
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=5)


class ExperienceDraft(StrictProfileModel):
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    start_date: PartialDate | None = None
    end_date: PartialDate | None = None
    is_current: bool = False
    highlights: list[EvidenceBackedStatement] = Field(default_factory=list, max_length=20)
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def current_role_has_no_end_date(self) -> "ExperienceDraft":
        if self.is_current and self.end_date is not None:
            raise ValueError("A current role cannot have an end date")
        return self


class SkillDraft(StrictProfileModel):
    name: str = Field(min_length=1, max_length=100)
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=5)


class QualificationDraft(StrictProfileModel):
    name: str = Field(min_length=1, max_length=200)
    kind: QualificationKind
    issuer: str | None = Field(default=None, max_length=200)
    awarded_date: PartialDate | None = None
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=5)

    @field_validator("name")
    @classmethod
    def degrees_belong_in_education(cls, value: str) -> str:
        degree_pattern = r"\b(?:ba|bsc|ma|msc|mba|phd|bachelor|master|doctorate)\b"
        if re.search(degree_pattern, value, flags=re.IGNORECASE):
            raise ValueError("Degrees belong under education, not qualifications")
        return value


class EducationDraft(StrictProfileModel):
    degree: str = Field(min_length=1, max_length=200)
    institution: str | None = Field(default=None, max_length=200)
    field_of_study: str | None = Field(default=None, max_length=200)
    start_date: PartialDate | None = None
    end_date: PartialDate | None = None
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=5)


class CountryDraft(StrictProfileModel):
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    name: str = Field(min_length=2, max_length=100)
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=3)


class IndustryDraft(StrictProfileModel):
    name: str = Field(min_length=2, max_length=150)
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=3)


class CandidateProfileDraft(StrictProfileModel):
    experiences: list[ExperienceDraft] = Field(default_factory=list, max_length=30)
    skills: list[SkillDraft] = Field(default_factory=list, max_length=100)
    qualifications: list[QualificationDraft] = Field(default_factory=list, max_length=50)
    education: list[EducationDraft] = Field(default_factory=list, max_length=20)
    country: CountryDraft | None = None
    industry: IndustryDraft | None = None


class CandidateExperience(ExperienceDraft):
    experience_id: UUID


class CandidateSkill(SkillDraft):
    skill_id: UUID


class CandidateQualification(QualificationDraft):
    qualification_id: UUID


class CandidateEducation(EducationDraft):
    education_id: UUID


class StandardSkill(StrictProfileModel):
    skill_id: UUID
    preferred_label: str = Field(min_length=1, max_length=150)
    source: SkillSource
    concept_uri: str = Field(min_length=1, max_length=300)
    standard_code: str | None = Field(default=None, max_length=50)
    aliases: list[str] = Field(min_length=1, max_length=30)


class SkillCatalog(StrictProfileModel):
    catalog_id: UUID
    version: str = Field(min_length=1, max_length=50)
    skills: list[StandardSkill] = Field(min_length=1)


class CandidateStandardSkill(StrictProfileModel):
    candidate_standard_skill_id: UUID
    standard_skill_id: UUID
    preferred_label: str
    source: SkillSource
    mapping_method: SkillMappingMethod = SkillMappingMethod.EXACT_ALIAS
    similarity: float = Field(default=1.0, ge=-1.0, le=1.0)
    extracted_names: list[str] = Field(default_factory=list, max_length=10)
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=5)


class CandidateEducationLevel(StrictProfileModel):
    education_level_id: UUID
    level: EducationLevel
    eqf_level: int = Field(ge=4, le=8)
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=5)


class CandidateCountry(CountryDraft):
    country_id: UUID


class StandardIndustry(StrictProfileModel):
    industry_id: UUID
    naics_code: str = Field(pattern=r"^(?:\d{2}|\d{2}-\d{2})$")
    preferred_label: str = Field(min_length=2, max_length=150)
    concept_uri: str = Field(min_length=1, max_length=300)
    aliases: list[str] = Field(min_length=1, max_length=30)


class IndustryCatalog(StrictProfileModel):
    catalog_id: UUID
    version: str = Field(min_length=1, max_length=50)
    industries: list[StandardIndustry] = Field(min_length=1)


class CandidateIndustry(StrictProfileModel):
    candidate_industry_id: UUID
    industry_id: UUID
    naics_code: str
    preferred_label: str
    evidence: list[EvidenceReference] = Field(min_length=1, max_length=3)


class CandidateProfile(StrictProfileModel):
    profile_id: UUID
    resume_id: UUID
    extractor_version: str
    featured_experience_id: UUID | None
    experiences: list[CandidateExperience]
    skills: list[CandidateSkill]
    standardized_skills: list[CandidateStandardSkill] = Field(default_factory=list)
    education_level: CandidateEducationLevel | None = None
    country: CandidateCountry | None = None
    industry: CandidateIndustry | None = None
    qualifications: list[CandidateQualification]
    education: list[CandidateEducation]
