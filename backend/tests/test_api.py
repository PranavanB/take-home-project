import time
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from app.config import Settings
from app.domain import ProcessingStage, SessionStatus
from app.main import create_app


class EmptyProfileGenerator:
    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        category = next(iter(json_schema["properties"]))
        return {category: None if category in {"country", "industry"} else []}


def make_pdf_bytes(text: str) -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output)
    document.drawString(72, 760, text)
    document.drawString(72, 740, "Python, FastAPI, Docker, PostgreSQL and cloud systems")
    document.save()
    return output.getvalue()


def test_upload_heartbeat_and_close_contract(tmp_path) -> None:
    dataset_root = Path(__file__).resolve().parents[2] / "seed" / "jobs"
    settings = Settings(
        session_root=tmp_path / "sessions",
        job_dataset_root=dataset_root,
        session_ttl_seconds=600,
        worker_poll_seconds=0.01,
    )

    with TestClient(create_app(settings, EmptyProfileGenerator())) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["job_fixture_count"] == 16
        assert health.json()["standard_skill_count"] == 56
        assert health.json()["industry_count"] == 20

        created = client.post(
            "/api/match-sessions",
            files={
                "resume": (
                    "resume.pdf",
                    make_pdf_bytes("Alex Morgan - Senior Software Engineer"),
                    "application/pdf",
                )
            },
        )
        assert created.status_code == 202
        session = created.json()
        session_id = session["match_session_id"]

        summary = session
        deadline = time.monotonic() + 2
        while summary["stage"] not in {"ready", "failed"}:
            assert time.monotonic() < deadline
            time.sleep(0.01)
            summary = client.get(f"/api/match-sessions/{session_id}").json()

        assert summary["stage"] == "ready"
        assert not (settings.session_root / session_id / "resume.pdf").exists()
        assert (settings.session_root / session_id / "extracted-document.json").is_file()
        assert (settings.session_root / session_id / "candidate-profile.json").is_file()

        profile = client.get(f"/api/match-sessions/{session_id}/profile")
        assert profile.status_code == 200
        assert profile.json()["resume_id"] == session["resume_id"]
        assert profile.json()["experiences"] == []

        heartbeat = client.post(f"/api/match-sessions/{session_id}/heartbeat")
        assert heartbeat.status_code == 200
        assert heartbeat.json()["status"] == "ready"

        stale_close = client.post(f"/api/match-sessions/{session_id}/close")
        assert stale_close.status_code == 204
        assert client.get(f"/api/match-sessions/{session_id}").status_code == 200

        closed = client.post(
            f"/api/match-sessions/{session_id}/close",
            headers={"X-Job-Matcher-Close-Reason": "user-reset"},
        )
        assert closed.status_code == 204
        assert client.get(f"/api/match-sessions/{session_id}").status_code == 404
        assert not (settings.session_root / session_id).exists()


def test_available_jobs_lists_all_public_roles_and_sources(tmp_path) -> None:
    dataset_root = Path(__file__).resolve().parents[2] / "seed" / "jobs"
    settings = Settings(session_root=tmp_path / "sessions", job_dataset_root=dataset_root)

    with TestClient(create_app(settings, EmptyProfileGenerator())) as client:
        response = client.get("/api/jobs")

    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 16
    assert jobs[0]["title"] == "Senior Backend Engineer"
    assert jobs[0]["company"] == "Aurora Labs"
    assert jobs[0]["minimum_education_level"] == "bachelors"
    assert jobs[0]["country_code"] == "GB"
    assert jobs[0]["industry_label"] == "Information"
    assert jobs[0]["location_label"] == "Manchester, UK"
    assert len(jobs[0]["summary"].split()) >= 35
    assert jobs[0]["responsibilities"]
    assert jobs[0]["required_qualifications"]
    assert jobs[0]["preferred_qualifications"]
    assert "required_skill_ids" not in jobs[0]
    assert len({job["job_id"] for job in jobs}) == 16
    sourced_jobs = [job for job in jobs if job["source_url"] is not None]
    assert len(sourced_jobs) == 10
    assert all(job["source_checked_at"] == "2026-08-23" for job in sourced_jobs)
    assert {
        "Registered Nurse",
        "Customer and Trading Manager – Online",
        "Chef de Partie",
        "Cleaning Operative",
        "Cabin Crew – Talent Pool",
    } <= {job["title"] for job in sourced_jobs}


def test_upload_rejects_non_public_format(tmp_path) -> None:
    dataset_root = Path(__file__).resolve().parents[2] / "seed" / "jobs"
    settings = Settings(session_root=tmp_path / "sessions", job_dataset_root=dataset_root)

    with TestClient(create_app(settings, EmptyProfileGenerator())) as client:
        response = client.post(
            "/api/match-sessions",
            files={"resume": ("resume.txt", b"Plain text resume", "text/plain")},
        )

    assert response.status_code == 415
    assert response.json()["detail"] == "Upload a PDF or DOCX file"


def test_upload_rejects_fake_pdf_before_creating_session(tmp_path) -> None:
    dataset_root = Path(__file__).resolve().parents[2] / "seed" / "jobs"
    settings = Settings(session_root=tmp_path / "sessions", job_dataset_root=dataset_root)

    with TestClient(create_app(settings, EmptyProfileGenerator())) as client:
        response = client.post(
            "/api/match-sessions",
            files={"resume": ("resume.pdf", b"not really a PDF", "application/pdf")},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "That file does not appear to be a valid PDF"
    assert list(settings.session_root.iterdir()) == []


def test_complete_pipeline_returns_exactly_three_results(tmp_path) -> None:
    dataset_root = Path(__file__).resolve().parents[2] / "seed" / "jobs"
    settings = Settings(
        session_root=tmp_path / "sessions",
        job_dataset_root=dataset_root,
        worker_poll_seconds=0.01,
    )

    with TestClient(create_app(settings, EmptyProfileGenerator())) as client:
        created = client.post(
            "/api/match-sessions",
            files={
                "resume": (
                    "resume.pdf",
                    make_pdf_bytes("Alex Morgan - Senior Software Engineer"),
                    "application/pdf",
                )
            },
        )
        session_id = created.json()["match_session_id"]
        deadline = time.monotonic() + 3
        summary = created.json()
        while summary["stage"] not in {"ready", "failed"}:
            assert time.monotonic() < deadline
            time.sleep(0.01)
            summary = client.get(f"/api/match-sessions/{session_id}").json()

        assert summary["stage"] == "ready"
        results = client.get(f"/api/match-sessions/{session_id}/results")
        assert results.status_code == 200
        assert len(results.json()["top_matches"]) == 3
        assert all(len(match["requirements"]) >= 7 for match in results.json()["top_matches"])


def test_failed_matching_session_can_retry_from_saved_profile(tmp_path) -> None:
    dataset_root = Path(__file__).resolve().parents[2] / "seed" / "jobs"
    settings = Settings(
        session_root=tmp_path / "sessions",
        job_dataset_root=dataset_root,
        worker_poll_seconds=0.01,
    )
    app = create_app(settings, EmptyProfileGenerator())

    with TestClient(app) as client:
        created = client.post(
            "/api/match-sessions",
            files={
                "resume": (
                    "resume.pdf",
                    make_pdf_bytes("Alex Morgan - Senior Software Engineer"),
                    "application/pdf",
                )
            },
        )
        session_id = created.json()["match_session_id"]
        deadline = time.monotonic() + 2
        summary = created.json()
        while summary["stage"] != "ready":
            assert time.monotonic() < deadline
            time.sleep(0.01)
            summary = client.get(f"/api/match-sessions/{session_id}").json()

        store = app.state.session_store
        manifest = store.read_manifest(session_id)
        manifest.status = SessionStatus.FAILED
        manifest.stage = ProcessingStage.FAILED
        manifest.attempt_count = 3
        manifest.error = "Temporary matching failure"
        store.write_manifest(manifest)

        retried = client.post(f"/api/match-sessions/{session_id}/retry")

        assert retried.status_code == 200
        assert retried.json()["status"] in {"processing", "ready"}
        assert retried.json()["stage"] in {"finding_matches", "ready"}
        assert retried.json()["error"] is None
