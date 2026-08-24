from pathlib import Path

import pytest

from app.catalog import load_skill_catalog
from app.domain import SkillMappingMethod
from app.skill_mapper import SkillVectorMapper


class SemanticEmbeddingGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str], str]] = []

    async def embed(
        self,
        *,
        model: str,
        texts: list[str],
        task: str,
    ) -> list[list[float]]:
        self.calls.append((model, texts, task))
        vectors: list[list[float]] = []
        for text in texts:
            value = text.casefold()
            if "orchestrating containers across clusters" in value:
                vectors.append([1.0, 0.0])
            elif "ambiguous container platform" in value:
                vectors.append([1.0, 1.0])
            elif "kubernetes" in value:
                vectors.append([1.0, 0.0])
            elif "docker" in value:
                vectors.append([0.0, 1.0])
            else:
                vectors.append([-1.0, 0.0])
        return vectors


def make_mapper() -> tuple[SkillVectorMapper, SemanticEmbeddingGateway]:
    catalog = load_skill_catalog(
        Path(__file__).resolve().parents[2] / "seed" / "skills" / "skills.json"
    )
    gateway = SemanticEmbeddingGateway()
    return (
        SkillVectorMapper(
            catalog=catalog,
            gateway=gateway,
            model="nomic-embed-text-v1.5",
            minimum_similarity=0.75,
            minimum_margin=0.05,
        ),
        gateway,
    )


@pytest.mark.asyncio
async def test_exact_alias_keeps_authoritative_skill_identity() -> None:
    mapper, gateway = make_mapper()

    mappings = await mapper.map_names(["K8s"])

    assert len(mappings) == 1
    assert mappings[0].standard_skill.preferred_label == "Kubernetes"
    assert mappings[0].method == SkillMappingMethod.EXACT_ALIAS
    assert mappings[0].similarity == 1.0
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_vector_similarity_maps_new_wording_to_catalogue_uuid() -> None:
    mapper, gateway = make_mapper()

    mappings = await mapper.map_names(["orchestrating containers across clusters"])

    assert len(mappings) == 1
    assert mappings[0].standard_skill.preferred_label == "Kubernetes"
    assert mappings[0].method == SkillMappingMethod.VECTOR
    assert mappings[0].similarity == pytest.approx(1.0)
    assert [call[2] for call in gateway.calls] == ["search_document", "search_query"]


@pytest.mark.asyncio
async def test_ambiguous_vector_result_is_left_unmapped() -> None:
    mapper, _ = make_mapper()

    mappings = await mapper.map_names(["ambiguous container platform"])

    assert mappings == []

