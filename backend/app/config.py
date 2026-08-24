from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Job Matcher API"
    llm_base_url: str = "http://127.0.0.1:8001/v1"
    llm_model: str = "job-matcher-llm"
    embedding_base_url: str | None = None
    embedding_model: str = "Snowflake/snowflake-arctic-embed-m-v2.0"
    skill_vector_minimum_similarity: float = Field(default=0.25, ge=0, le=1)
    skill_vector_minimum_margin: float = Field(default=0.04, ge=0, le=1)
    session_root: Path = Field(default=Path(".sessions"))
    session_ttl_seconds: int = Field(default=600, ge=60, le=86_400)
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    max_document_pages: int = Field(default=25, ge=1, le=500)
    max_docx_uncompressed_bytes: int = Field(default=50 * 1024 * 1024, ge=1024)
    worker_poll_seconds: float = Field(default=0.5, ge=0.01, le=60)
    worker_lease_seconds: int = Field(default=30, ge=5, le=3600)
    job_dataset_root: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[2] / "seed" / "jobs"
    )
    skill_catalog_path: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[2]
        / "seed"
        / "skills"
        / "skills.json"
    )
    industry_catalog_path: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[2]
        / "seed"
        / "industries"
        / "naics-2022.json"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
