from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.profile import EducationLevel


class SessionStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    CLOSING = "closing"


class ProcessingStage(StrEnum):
    QUEUED = "queued"
    READING_CV = "reading_cv"
    BUILDING_PROFILE = "building_profile"
    FINDING_MATCHES = "finding_matches"
    READY = "ready"
    FAILED = "failed"


class DocumentType(StrEnum):
    PDF = "pdf"
    DOCX = "docx"


class ExtractedBlock(BaseModel):
    block_id: UUID
    ordinal: int = Field(ge=1)
    source_label: str
    page_number: int | None = Field(default=None, ge=1)
    kind: str
    text: str


class ExtractedDocument(BaseModel):
    reader_version: str
    resume_id: UUID
    document_type: DocumentType
    page_count: int | None = Field(default=None, ge=1)
    char_count: int = Field(ge=1)
    blocks: list[ExtractedBlock]

    def combined_text(self) -> str:
        return "\n\n".join(f"[{block.source_label}]\n{block.text}" for block in self.blocks)


class SessionManifest(BaseModel):
    match_session_id: UUID
    resume_id: UUID
    ingest_job_id: UUID
    original_filename: str
    stored_filename: str
    content_type: str
    content_length: int
    status: SessionStatus = SessionStatus.QUEUED
    stage: ProcessingStage = ProcessingStage.QUEUED
    attempt_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_heartbeat_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    worker_lease_expires_at: datetime | None = None
    extracted_document_filename: str | None = None
    profile_filename: str | None = None
    match_results_filename: str | None = None
    raw_upload_deleted_at: datetime | None = None
    error: str | None = None


class SessionSummary(BaseModel):
    match_session_id: UUID
    resume_id: UUID
    ingest_job_id: UUID
    status: SessionStatus
    stage: ProcessingStage
    attempt_count: int
    expires_at: datetime
    error: str | None = None

    @classmethod
    def from_manifest(cls, manifest: SessionManifest) -> "SessionSummary":
        return cls(**manifest.model_dump())


class JobFixture(BaseModel):
    job_id: UUID
    title: str
    company: str
    summary: str
    responsibilities: list[str]
    required_qualifications: list[str]
    preferred_qualifications: list[str]
    minimum_education_level: EducationLevel | None
    required_skill_ids: list[UUID]
    preferred_skill_ids: list[UUID]
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    industry_id: UUID
    location_label: str | None = None
    work_pattern: str | None = None
    employment_type: str | None = None
    salary: str | None = None
    source_url: str | None = None
    source_checked_at: date | None = None


class AvailableJob(BaseModel):
    job_id: UUID
    title: str
    company: str
    summary: str
    responsibilities: list[str]
    required_qualifications: list[str]
    preferred_qualifications: list[str]
    minimum_education_level: EducationLevel | None
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    industry_label: str
    location_label: str | None
    work_pattern: str | None
    employment_type: str | None
    salary: str | None
    source_url: str | None
    source_checked_at: date | None
