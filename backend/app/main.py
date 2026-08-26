import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

import structlog
from fastapi import FastAPI

from app.catalog import load_industry_catalog, load_job_dataset, load_skill_catalog
from app.config import Settings, get_settings
from app.gateway import OpenAIEmbeddingGateway, VLLMProfileDraftGenerator
from app.matcher import MatchAnalyzer
from app.profile_extractor import ProfileDraftGenerator, ProfileExtractor
from app.routes.jobs import router as jobs_router
from app.routes.sessions import router as sessions_router
from app.session_store import SessionStore
from app.skill_mapper import SkillVectorMapper
from app.worker import DocumentWorker

logger = structlog.get_logger()


async def cleanup_loop(store: SessionStore) -> None:
    while True:
        deleted = store.cleanup_expired()
        for session_id in deleted:
            logger.info("expired_session_deleted", match_session_id=str(session_id))
        await asyncio.sleep(30)


def create_app(
    settings: Settings | None = None,
    profile_generator: ProfileDraftGenerator | None = None,
) -> FastAPI:
    resolved = settings or get_settings()
    resolved_profile_generator = profile_generator or VLLMProfileDraftGenerator(
        base_url=resolved.llm_base_url,
        model=resolved.llm_model,
    )
    skill_catalog = load_skill_catalog(resolved.skill_catalog_path)
    industry_catalog = load_industry_catalog(resolved.industry_catalog_path)
    skill_mapper = (
        SkillVectorMapper(
            catalog=skill_catalog,
            gateway=OpenAIEmbeddingGateway(
                base_url=resolved.embedding_base_url,
                model=resolved.embedding_model,
            ),
            model=resolved.embedding_model,
            minimum_similarity=resolved.skill_vector_minimum_similarity,
            minimum_margin=resolved.skill_vector_minimum_margin,
        )
        if resolved.embedding_base_url
        else None
    )
    match_analyzer = MatchAnalyzer(skill_catalog, industry_catalog)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = resolved
        app.state.session_store = SessionStore(resolved.session_root, resolved.session_ttl_seconds)
        app.state.jobs = load_job_dataset(resolved.job_dataset_root)
        app.state.skill_catalog = skill_catalog
        app.state.industry_catalog = industry_catalog
        document_worker = DocumentWorker(
            store=app.state.session_store,
            max_document_pages=resolved.max_document_pages,
            max_docx_uncompressed_bytes=resolved.max_docx_uncompressed_bytes,
            poll_seconds=resolved.worker_poll_seconds,
            lease_seconds=resolved.worker_lease_seconds,
            profile_extractor=ProfileExtractor(
                resolved_profile_generator,
                skill_catalog,
                industry_catalog,
                skill_mapper,
            ),
            match_analyzer=match_analyzer,
            jobs=app.state.jobs,
        )
        cleanup_task = asyncio.create_task(cleanup_loop(app.state.session_store))
        worker_task = asyncio.create_task(document_worker.run())
        try:
            yield
        finally:
            cleanup_task.cancel()
            worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task
            with suppress(asyncio.CancelledError):
                await worker_task

    app = FastAPI(title=resolved.app_name, version="0.1.0", lifespan=lifespan)
    app.include_router(jobs_router)
    app.include_router(sessions_router)

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "job_fixture_count": len(app.state.jobs),
            "standard_skill_count": len(app.state.skill_catalog.skills),
            "skill_catalog_version": app.state.skill_catalog.version,
            "industry_count": len(app.state.industry_catalog.industries),
            "industry_catalog_version": app.state.industry_catalog.version,
            "job_requirements_version": app.state.jobs[0].requirements_version,
            "skill_mapping_method": (
                "exact_alias_then_vector" if skill_mapper is not None else "exact_alias"
            ),
            "embedding_model": (
                resolved.embedding_model if skill_mapper is not None else None
            ),
            "matching_method": "exact_database_join",
        }

    return app


app = create_app()
