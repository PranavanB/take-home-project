import os
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel

from app.domain import ProcessingStage, SessionManifest, SessionStatus


class SessionNotFoundError(FileNotFoundError):
    pass


class SessionRetryUnavailableError(RuntimeError):
    pass


class SessionStore:
    def __init__(self, root: Path, ttl_seconds: int) -> None:
        self.root = root.resolve()
        self.ttl_seconds = ttl_seconds
        self.root.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        *,
        original_filename: str,
        content_type: str,
        content: bytes,
    ) -> SessionManifest:
        session_id = uuid4()
        resume_id = uuid4()
        ingest_job_id = uuid4()
        session_dir = self._session_dir(session_id)
        session_dir.mkdir(mode=0o700)

        suffix = Path(original_filename).suffix.lower()
        stored_filename = f"resume{suffix}"
        upload_path = session_dir / stored_filename
        temporary_upload = session_dir / f"upload.{uuid4()}.tmp"
        temporary_upload.write_bytes(content)
        os.replace(temporary_upload, upload_path)

        now = datetime.now(UTC)
        manifest = SessionManifest(
            match_session_id=session_id,
            resume_id=resume_id,
            ingest_job_id=ingest_job_id,
            original_filename=Path(original_filename).name,
            stored_filename=stored_filename,
            content_type=content_type,
            content_length=len(content),
            created_at=now,
            last_heartbeat_at=now,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
        )
        self.write_manifest(manifest)
        return manifest

    def read_manifest(self, session_id: UUID) -> SessionManifest:
        path = self._session_dir(session_id) / "manifest.json"
        if not path.is_file():
            raise SessionNotFoundError(str(session_id))
        return SessionManifest.model_validate_json(path.read_text(encoding="utf-8"))

    def write_manifest(self, manifest: SessionManifest) -> None:
        session_dir = self._session_dir(manifest.match_session_id)
        if not session_dir.is_dir():
            raise SessionNotFoundError(str(manifest.match_session_id))
        target = session_dir / "manifest.json"
        temporary = session_dir / f"manifest.{uuid4()}.tmp"
        temporary.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        os.replace(temporary, target)

    def heartbeat(self, session_id: UUID) -> SessionManifest:
        manifest = self.read_manifest(session_id)
        if manifest.status == SessionStatus.CLOSING:
            raise SessionNotFoundError(str(session_id))
        now = datetime.now(UTC)
        manifest.last_heartbeat_at = now
        manifest.expires_at = now + timedelta(seconds=self.ttl_seconds)
        self.write_manifest(manifest)
        return manifest

    def retry(self, session_id: UUID) -> SessionManifest:
        manifest = self.read_manifest(session_id)
        if manifest.status != SessionStatus.FAILED:
            raise SessionRetryUnavailableError("Only failed sessions can be retried")

        if manifest.profile_filename and self.artifact_exists(
            session_id, manifest.profile_filename
        ):
            next_stage = ProcessingStage.FINDING_MATCHES
        elif manifest.extracted_document_filename and self.artifact_exists(
            session_id, manifest.extracted_document_filename
        ):
            next_stage = ProcessingStage.BUILDING_PROFILE
        elif self.upload_path(manifest).is_file():
            next_stage = ProcessingStage.QUEUED
        else:
            raise SessionRetryUnavailableError("No recoverable session data remains")

        now = datetime.now(UTC)
        manifest.status = (
            SessionStatus.QUEUED
            if next_stage == ProcessingStage.QUEUED
            else SessionStatus.PROCESSING
        )
        manifest.stage = next_stage
        manifest.attempt_count = 0
        manifest.last_heartbeat_at = now
        manifest.expires_at = now + timedelta(seconds=self.ttl_seconds)
        manifest.worker_lease_expires_at = None
        manifest.error = None
        self.write_manifest(manifest)
        return manifest

    def delete(self, session_id: UUID) -> None:
        session_dir = self._session_dir(session_id)
        if session_dir.is_dir():
            shutil.rmtree(session_dir)

    def iter_manifests(self) -> list[SessionManifest]:
        manifests: list[SessionManifest] = []
        for directory in self.root.iterdir():
            if not directory.is_dir():
                continue
            try:
                manifests.append(self.read_manifest(UUID(directory.name)))
            except (ValueError, OSError, SessionNotFoundError):
                continue
        return manifests

    def upload_path(self, manifest: SessionManifest) -> Path:
        return self._artifact_path(manifest.match_session_id, manifest.stored_filename)

    def delete_upload(self, manifest: SessionManifest) -> None:
        self.upload_path(manifest).unlink(missing_ok=True)

    def artifact_exists(self, session_id: UUID, filename: str) -> bool:
        return self._artifact_path(session_id, filename).is_file()

    def read_artifact(self, session_id: UUID, filename: str) -> str:
        path = self._artifact_path(session_id, filename)
        if not path.is_file():
            raise SessionNotFoundError(str(session_id))
        return path.read_text(encoding="utf-8")

    def write_model_artifact(self, session_id: UUID, filename: str, value: BaseModel) -> None:
        target = self._artifact_path(session_id, filename)
        if not target.parent.is_dir():
            raise SessionNotFoundError(str(session_id))
        temporary = target.parent / f"artifact.{uuid4()}.tmp"
        try:
            temporary.write_text(value.model_dump_json(indent=2), encoding="utf-8")
            os.replace(temporary, target)
        except FileNotFoundError as exc:
            raise SessionNotFoundError(str(session_id)) from exc

    def cleanup_expired(self, now: datetime | None = None) -> list[UUID]:
        current = now or datetime.now(UTC)
        deleted: list[UUID] = []
        for directory in self.root.iterdir():
            if not directory.is_dir():
                continue
            try:
                session_id = UUID(directory.name)
            except ValueError:
                continue
            try:
                manifest = self.read_manifest(session_id)
            except (ValueError, OSError, SessionNotFoundError):
                modified = datetime.fromtimestamp(directory.stat().st_mtime, UTC)
                if modified + timedelta(seconds=self.ttl_seconds) <= current:
                    self.delete(session_id)
                    deleted.append(session_id)
                continue
            if manifest.expires_at <= current:
                self.delete(session_id)
                deleted.append(session_id)
        return deleted

    def _session_dir(self, session_id: UUID) -> Path:
        candidate = (self.root / str(session_id)).resolve()
        if candidate.parent != self.root:
            raise ValueError("Session path escaped configured root")
        return candidate

    def _artifact_path(self, session_id: UUID, filename: str) -> Path:
        session_dir = self._session_dir(session_id)
        candidate = (session_dir / filename).resolve()
        if candidate.parent != session_dir:
            raise ValueError("Artifact path escaped session directory")
        return candidate
