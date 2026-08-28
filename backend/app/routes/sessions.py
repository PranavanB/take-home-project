import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

import httpx
import structlog
from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.document_reader import DocumentReadError, validate_upload_bytes
from app.domain import (
    CandidateProfile,
    ChatMessage,
    ChatRole,
    MatchChatRequest,
    MatchChatResponse,
    MatchResults,
    SessionStatus,
    SessionSummary,
)
from app.gateway import LLMChatError
from app.match_chat import build_match_chat_system_prompt
from app.session_store import (
    SessionNotFoundError,
    SessionRetryUnavailableError,
    SessionStore,
)

router = APIRouter(prefix="/api/match-sessions", tags=["match-sessions"])
logger = structlog.get_logger()

ALLOWED_SUFFIXES = {".pdf", ".docx"}
EXPLICIT_CLOSE_REASON = "user-reset"


def get_store(request: Request) -> SessionStore:
    return request.app.state.session_store


@router.post("", response_model=SessionSummary, status_code=status.HTTP_202_ACCEPTED)
async def create_match_session(
    request: Request,
    resume: Annotated[UploadFile, File()],
) -> SessionSummary:
    suffix = Path(resume.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="Upload a PDF or DOCX file")

    content = await resume.read(request.app.state.settings.max_upload_bytes + 1)
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")
    if len(content) > request.app.state.settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="The uploaded file is too large")
    try:
        validate_upload_bytes(
            filename=resume.filename or f"resume{suffix}",
            content=content,
            max_docx_uncompressed_bytes=(
                request.app.state.settings.max_docx_uncompressed_bytes
            ),
        )
    except DocumentReadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    manifest = get_store(request).create(
        original_filename=resume.filename or f"resume{suffix}",
        content_type=resume.content_type or "application/octet-stream",
        content=content,
    )
    return SessionSummary.from_manifest(manifest)


@router.get("/{session_id}", response_model=SessionSummary)
def get_match_session(session_id: UUID, request: Request) -> SessionSummary:
    try:
        return SessionSummary.from_manifest(get_store(request).read_manifest(session_id))
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Match session not found") from exc


@router.get("/{session_id}/profile", response_model=CandidateProfile)
def get_candidate_profile(session_id: UUID, request: Request) -> CandidateProfile:
    store = get_store(request)
    try:
        manifest = store.read_manifest(session_id)
        if manifest.profile_filename is None:
            raise HTTPException(status_code=404, detail="Candidate profile is not ready")
        return CandidateProfile.model_validate_json(
            store.read_artifact(session_id, manifest.profile_filename)
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Match session not found") from exc


@router.get("/{session_id}/results", response_model=MatchResults)
def get_match_results(session_id: UUID, request: Request) -> MatchResults:
    store = get_store(request)
    try:
        manifest = store.read_manifest(session_id)
        if manifest.match_results_filename is None:
            raise HTTPException(status_code=404, detail="Match results are not ready")
        return MatchResults.model_validate_json(
            store.read_artifact(session_id, manifest.match_results_filename)
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Match session not found") from exc


@router.post("/{session_id}/chat", response_model=MatchChatResponse)
async def ask_about_match(
    session_id: UUID,
    payload: MatchChatRequest,
    request: Request,
) -> MatchChatResponse:
    store = get_store(request)
    try:
        manifest = store.heartbeat(session_id)
        if manifest.status != SessionStatus.READY:
            raise HTTPException(status_code=409, detail="Match results are not ready")
        if manifest.profile_filename is None or manifest.match_results_filename is None:
            raise HTTPException(status_code=409, detail="Match results are not ready")
        profile = CandidateProfile.model_validate_json(
            store.read_artifact(session_id, manifest.profile_filename)
        )
        results = MatchResults.model_validate_json(
            store.read_artifact(session_id, manifest.match_results_filename)
        )
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Match session not found") from exc

    match = next(
        (
            item
            for item in results.top_matches
            if item.match_result_id == payload.match_result_id
        ),
        None,
    )
    if match is None:
        raise HTTPException(status_code=404, detail="Selected match not found")

    try:
        answer = await request.app.state.chat_generator.generate(
            system_prompt=build_match_chat_system_prompt(profile, match),
            messages=payload.messages,
        )
    except (httpx.HTTPError, LLMChatError) as exc:
        logger.warning(
            "match_chat_generation_failed",
            match_session_id=str(session_id),
            match_result_id=str(payload.match_result_id),
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="The career assistant is temporarily unavailable",
        ) from exc

    return MatchChatResponse(
        match_result_id=match.match_result_id,
        message=ChatMessage(
            message_id=uuid4(),
            role=ChatRole.ASSISTANT,
            content=answer,
        ),
    )


@router.post("/{session_id}/heartbeat", response_model=SessionSummary)
def heartbeat(session_id: UUID, request: Request) -> SessionSummary:
    try:
        return SessionSummary.from_manifest(get_store(request).heartbeat(session_id))
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Match session not found") from exc


@router.post("/{session_id}/retry", response_model=SessionSummary)
def retry_match_session(session_id: UUID, request: Request) -> SessionSummary:
    try:
        return SessionSummary.from_manifest(get_store(request).retry(session_id))
    except SessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Match session not found") from exc
    except SessionRetryUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{session_id}/close", status_code=status.HTTP_204_NO_CONTENT)
def close_match_session(session_id: UUID, request: Request) -> Response:
    store = get_store(request)
    close_reason = request.headers.get("x-job-matcher-close-reason")
    if close_reason != EXPLICIT_CLOSE_REASON:
        with suppress(SessionNotFoundError):
            manifest = store.read_manifest(session_id)
            logger.info(
                "session_close_ignored",
                match_session_id=str(session_id),
                status=manifest.status,
                stage=manifest.stage,
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    with suppress(SessionNotFoundError):
        manifest = store.read_manifest(session_id)
        logger.info(
            "session_close_accepted",
            match_session_id=str(session_id),
            status=manifest.status,
            stage=manifest.stage,
        )
    store.delete(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{session_id}/events")
def session_events(session_id: UUID, request: Request) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        last_payload = ""
        while True:
            if await request.is_disconnected():
                break
            try:
                summary = SessionSummary.from_manifest(get_store(request).read_manifest(session_id))
            except SessionNotFoundError:
                yield 'event: closed\ndata: {"status":"closed"}\n\n'
                break
            payload = summary.model_dump_json()
            if payload != last_payload:
                yield f"event: status\ndata: {json.dumps(json.loads(payload))}\n\n"
                last_payload = payload
            if summary.status in {"ready", "failed", "closing"}:
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
