from pathlib import Path
from typing import Any

import pytest

from app.catalog import load_job_dataset, load_skill_catalog
from app.job_skill_extractor import JobSkillNormalizer
from app.skill_mapper import SkillVectorMapper


class JobGenerator:
    def __init__(self) -> None:
        self.calls = 0
        self.user_prompt = ""
        self.schema: dict[str, Any] = {}

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls += 1
        self.user_prompt = user_prompt
        self.schema = json_schema
        return {
            "required_skills": ["Python", "API development"],
            "preferred_skills": ["Systems Analysis"],
        }


class UnusedEmbeddingGateway:
    async def embed(self, **kwargs: Any) -> list[list[float]]:
        raise AssertionError("Exact aliases should not call the embedding service")


@pytest.mark.asyncio
async def test_job_skills_are_llm_extracted_mapped_and_cached() -> None:
    seed_root = Path(__file__).resolve().parents[2] / "seed"
    job = load_job_dataset(seed_root / "jobs")[0]
    catalog = load_skill_catalog(seed_root / "skills" / "skills.json")
    generator = JobGenerator()
    mapper = SkillVectorMapper(
        catalog=catalog,
        gateway=UnusedEmbeddingGateway(),
        model="test-embedding",
    )
    normalizer = JobSkillNormalizer(generator=generator, mapper=mapper)

    first = await normalizer.normalize(job)
    second = await normalizer.normalize(job)

    by_label = {skill.preferred_label: skill.skill_id for skill in catalog.skills}
    assert first == second
    assert first.required_skill_ids == [
        by_label["Python (computer programming)"],
        by_label["design application interfaces"],
    ]
    assert first.preferred_skill_ids == [by_label["Systems Analysis"]]
    assert generator.calls == 1
    assert job.title in generator.user_prompt
    assert "Own API reliability" in generator.user_prompt
    assert generator.schema["additionalProperties"] is False

