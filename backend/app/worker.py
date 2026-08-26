import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog

from app.document_reader import DocumentReadError, read_document
from app.domain import (
    CandidateProfile,
    ExtractedDocument,
    JobFixture,
    MatchResults,
    ProcessingStage,
    SessionManifest,
    SessionStatus,
)
from app.matcher import MatchAnalyzer
from app.profile_extractor import ProfileExtractor
from app.session_store import SessionNotFoundError, SessionStore

EXTRACTED_DOCUMENT_FILENAME = "extracted-document.json"
CANDIDATE_PROFILE_FILENAME = "candidate-profile.json"
MATCH_RESULTS_FILENAME = "match-results.json"
MAX_ATTEMPTS = 3

logger = structlog.get_logger()


class DocumentWorker:
    def __init__(
        self,
        *,
        store: SessionStore,
        max_document_pages: int,
        max_docx_uncompressed_bytes: int,
        poll_seconds: float,
        lease_seconds: int,
        profile_extractor: ProfileExtractor,
        match_analyzer: MatchAnalyzer | None = None,
        jobs: list[JobFixture] | None = None,
    ) -> None:
        self.store = store
        self.max_document_pages = max_document_pages
        self.max_docx_uncompressed_bytes = max_docx_uncompressed_bytes
        self.poll_seconds = poll_seconds
        self.lease_seconds = lease_seconds
        self.profile_extractor = profile_extractor
        self.match_analyzer = match_analyzer
        self.jobs = jobs or []

    async def run(self) -> None:
        while True:
            for manifest in self.store.iter_manifests():
                if self._claimable(manifest):
                    await self.process_session(manifest.match_session_id)
            await asyncio.sleep(self.poll_seconds)

    async def process_session(self, session_id: UUID) -> None:
        try:
            manifest = self._claim(session_id)
            if manifest is None:
                return
            if manifest.stage == ProcessingStage.READING_CV:
                await self._read_cv(manifest)
            elif manifest.stage == ProcessingStage.BUILDING_PROFILE:
                await self._build_profile(manifest)
            elif manifest.stage == ProcessingStage.FINDING_MATCHES:
                await self._find_matches(manifest)
        except DocumentReadError as exc:
            self._fail(session_id, str(exc))
        except SessionNotFoundError:
            return
        except Exception:
            logger.exception(
                "session_processing_unexpected_error",
                match_session_id=str(session_id),
            )
            self._retry_or_fail(session_id)

    def _claimable(self, manifest: SessionManifest) -> bool:
        if manifest.status == SessionStatus.QUEUED:
            return True
        claimable_stages = {ProcessingStage.READING_CV, ProcessingStage.BUILDING_PROFILE}
        if self.match_analyzer is not None:
            claimable_stages.add(ProcessingStage.FINDING_MATCHES)
        return (
            manifest.status == SessionStatus.PROCESSING
            and manifest.stage in claimable_stages
            and (
                manifest.worker_lease_expires_at is None
                or manifest.worker_lease_expires_at <= datetime.now(UTC)
            )
        )

    def _claim(self, session_id: UUID) -> SessionManifest | None:
        manifest = self.store.read_manifest(session_id)
        if not self._claimable(manifest):
            return None
        if manifest.attempt_count >= MAX_ATTEMPTS:
            self._fail(session_id, self._failure_message(manifest.stage))
            return None
        manifest.status = SessionStatus.PROCESSING
        if manifest.stage in {ProcessingStage.QUEUED, ProcessingStage.READING_CV}:
            manifest.stage = ProcessingStage.READING_CV
        manifest.attempt_count += 1
        manifest.worker_lease_expires_at = datetime.now(UTC) + timedelta(
            seconds=self.lease_seconds
        )
        manifest.error = None
        self.store.write_manifest(manifest)
        return manifest

    def _retry_or_fail(self, session_id: UUID) -> None:
        with suppress(SessionNotFoundError):
            manifest = self.store.read_manifest(session_id)
            failed_stage = manifest.stage
            manifest.worker_lease_expires_at = None
            if manifest.attempt_count >= MAX_ATTEMPTS:
                manifest.status = SessionStatus.FAILED
                manifest.stage = ProcessingStage.FAILED
                manifest.error = self._failure_message(failed_stage)
            elif manifest.stage == ProcessingStage.BUILDING_PROFILE:
                manifest.status = SessionStatus.PROCESSING
                manifest.error = "A temporary model error occurred; retrying"
            elif manifest.stage == ProcessingStage.FINDING_MATCHES:
                manifest.status = SessionStatus.PROCESSING
                manifest.error = "A temporary matching error occurred; retrying"
            else:
                manifest.status = SessionStatus.QUEUED
                manifest.stage = ProcessingStage.QUEUED
                manifest.error = "A temporary error occurred; retrying"
            self.store.write_manifest(manifest)

    def _fail(self, session_id: UUID, message: str) -> None:
        with suppress(SessionNotFoundError):
            manifest = self.store.read_manifest(session_id)
            manifest.status = SessionStatus.FAILED
            manifest.stage = ProcessingStage.FAILED
            manifest.worker_lease_expires_at = None
            manifest.error = message
            self.store.write_manifest(manifest)

    async def _read_cv(self, manifest: SessionManifest) -> None:
        session_id = manifest.match_session_id
        if self.store.artifact_exists(session_id, EXTRACTED_DOCUMENT_FILENAME):
            ExtractedDocument.model_validate_json(
                self.store.read_artifact(session_id, EXTRACTED_DOCUMENT_FILENAME)
            )
        else:
            document = await asyncio.to_thread(
                read_document,
                self.store.upload_path(manifest),
                resume_id=manifest.resume_id,
                max_pages=self.max_document_pages,
                max_docx_uncompressed_bytes=self.max_docx_uncompressed_bytes,
            )
            self.store.write_model_artifact(session_id, EXTRACTED_DOCUMENT_FILENAME, document)

        self.store.delete_upload(manifest)
        completed = self.store.read_manifest(session_id)
        completed.status = SessionStatus.PROCESSING
        completed.stage = ProcessingStage.BUILDING_PROFILE
        completed.attempt_count = 0
        completed.extracted_document_filename = EXTRACTED_DOCUMENT_FILENAME
        completed.raw_upload_deleted_at = datetime.now(UTC)
        completed.worker_lease_expires_at = None
        completed.error = None
        self.store.write_manifest(completed)
        logger.info(
            "cv_read",
            match_session_id=str(session_id),
            resume_id=str(completed.resume_id),
        )

    async def _build_profile(self, manifest: SessionManifest) -> None:
        session_id = manifest.match_session_id
        if self.store.artifact_exists(session_id, CANDIDATE_PROFILE_FILENAME):
            profile = CandidateProfile.model_validate_json(
                self.store.read_artifact(session_id, CANDIDATE_PROFILE_FILENAME)
            )
        else:
            document = ExtractedDocument.model_validate_json(
                self.store.read_artifact(session_id, EXTRACTED_DOCUMENT_FILENAME)
            )
            profile = await self.profile_extractor.extract(document)
            self.store.write_model_artifact(session_id, CANDIDATE_PROFILE_FILENAME, profile)

        completed = self.store.read_manifest(session_id)
        completed.status = SessionStatus.PROCESSING
        completed.stage = ProcessingStage.FINDING_MATCHES
        completed.attempt_count = 0
        completed.profile_filename = CANDIDATE_PROFILE_FILENAME
        completed.worker_lease_expires_at = None
        completed.error = None
        self.store.write_manifest(completed)
        logger.info(
            "profile_built",
            match_session_id=str(session_id),
            resume_id=str(profile.resume_id),
            profile_id=str(profile.profile_id),
        )

    async def _find_matches(self, manifest: SessionManifest) -> None:
        if self.match_analyzer is None:
            return
        session_id = manifest.match_session_id
        if self.store.artifact_exists(session_id, MATCH_RESULTS_FILENAME):
            MatchResults.model_validate_json(
                self.store.read_artifact(session_id, MATCH_RESULTS_FILENAME)
            )
        else:
            profile = CandidateProfile.model_validate_json(
                self.store.read_artifact(session_id, CANDIDATE_PROFILE_FILENAME)
            )
            results = await self.match_analyzer.analyze(profile=profile, jobs=self.jobs)
            self.store.write_model_artifact(session_id, MATCH_RESULTS_FILENAME, results)

        completed = self.store.read_manifest(session_id)
        completed.status = SessionStatus.READY
        completed.stage = ProcessingStage.READY
        completed.attempt_count = 0
        completed.match_results_filename = MATCH_RESULTS_FILENAME
        completed.worker_lease_expires_at = None
        completed.error = None
        self.store.write_manifest(completed)
        logger.info("matches_built", match_session_id=str(session_id), result_count=3)

    @staticmethod
    def _failure_message(stage: ProcessingStage) -> str:
        if stage == ProcessingStage.BUILDING_PROFILE:
            return "We could not build a profile from this CV after several attempts"
        if stage == ProcessingStage.FINDING_MATCHES:
            return "We could not match this CV after several attempts"
        return "We could not read this CV after several attempts"
