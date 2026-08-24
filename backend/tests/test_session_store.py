import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.session_store import SessionNotFoundError, SessionStore


def test_session_create_heartbeat_and_delete(tmp_path) -> None:
    store = SessionStore(tmp_path, ttl_seconds=600)
    manifest = store.create(
        original_filename="resume.md",
        content_type="text/markdown",
        content=b"# Resume",
    )

    assert store.read_manifest(manifest.match_session_id).content_length == 8
    heartbeat = store.heartbeat(manifest.match_session_id)
    assert heartbeat.expires_at > manifest.expires_at

    store.delete(manifest.match_session_id)
    try:
        store.read_manifest(manifest.match_session_id)
    except SessionNotFoundError:
        pass
    else:
        raise AssertionError("Deleted session remained readable")


def test_deleted_session_rejects_new_artifact(tmp_path) -> None:
    store = SessionStore(tmp_path, ttl_seconds=600)
    manifest = store.create(
        original_filename="resume.pdf",
        content_type="application/pdf",
        content=b"temporary",
    )
    store.delete(manifest.match_session_id)

    try:
        store.write_model_artifact(manifest.match_session_id, "late.json", manifest)
    except SessionNotFoundError:
        pass
    else:
        raise AssertionError("Deleted session accepted a late worker artifact")


def test_cleanup_expired_session(tmp_path) -> None:
    store = SessionStore(tmp_path, ttl_seconds=600)
    manifest = store.create(
        original_filename="resume.txt",
        content_type="text/plain",
        content=b"resume",
    )
    deleted = store.cleanup_expired(now=datetime.now(UTC) + timedelta(hours=1))
    assert deleted == [manifest.match_session_id]


def test_cleanup_removes_old_uuid_directory_without_manifest(tmp_path) -> None:
    store = SessionStore(tmp_path, ttl_seconds=600)
    session_id = uuid4()
    orphan = tmp_path / str(session_id)
    orphan.mkdir()
    (orphan / "resume.pdf").write_bytes(b"private data")
    old = (datetime.now(UTC) - timedelta(hours=1)).timestamp()
    os.utime(orphan, (old, old))

    deleted = store.cleanup_expired()

    assert deleted == [session_id]
    assert not orphan.exists()
