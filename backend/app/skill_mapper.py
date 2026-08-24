import asyncio
import math
from dataclasses import dataclass
from typing import Protocol

from app.domain import SkillCatalog, SkillMappingMethod, StandardSkill


class EmbeddingGateway(Protocol):
    async def embed(
        self,
        *,
        model: str,
        texts: list[str],
        task: str,
    ) -> list[list[float]]: ...


@dataclass(frozen=True)
class SkillMapping:
    input_name: str
    standard_skill: StandardSkill
    method: SkillMappingMethod
    similarity: float


class SkillVectorMapper:
    def __init__(
        self,
        *,
        catalog: SkillCatalog,
        gateway: EmbeddingGateway,
        model: str,
        minimum_similarity: float = 0.25,
        minimum_margin: float = 0.04,
    ) -> None:
        if not 0 <= minimum_similarity <= 1:
            raise ValueError("minimum_similarity must be between zero and one")
        if not 0 <= minimum_margin <= 1:
            raise ValueError("minimum_margin must be between zero and one")
        self.catalog = catalog
        self.gateway = gateway
        self.model = model
        self.minimum_similarity = minimum_similarity
        self.minimum_margin = minimum_margin
        self._catalog_vectors: list[list[float]] | None = None
        self._catalog_lock = asyncio.Lock()
        self._aliases = {
            _normalise(alias): skill
            for skill in catalog.skills
            for alias in skill.aliases
        }

    async def map_names(self, names: list[str]) -> list[SkillMapping]:
        results: list[SkillMapping | None] = [None] * len(names)
        unresolved: list[tuple[int, str]] = []
        for index, name in enumerate(names):
            exact = self._aliases.get(_normalise(name))
            if exact is not None:
                results[index] = SkillMapping(
                    input_name=name,
                    standard_skill=exact,
                    method=SkillMappingMethod.EXACT_ALIAS,
                    similarity=1.0,
                )
            else:
                unresolved.append((index, name))

        if unresolved:
            catalog_vectors = await self._get_catalog_vectors()
            query_vectors = await self.gateway.embed(
                model=self.model,
                texts=[name for _, name in unresolved],
                task="search_query",
            )
            for (result_index, name), query_vector in zip(
                unresolved,
                query_vectors,
                strict=True,
            ):
                scored = sorted(
                    (
                        (_cosine_similarity(query_vector, vector), skill)
                        for skill, vector in zip(
                            self.catalog.skills,
                            catalog_vectors,
                            strict=True,
                        )
                    ),
                    key=lambda item: (-item[0], item[1].preferred_label.casefold()),
                )
                best_score, best_skill = scored[0]
                runner_up_score = scored[1][0] if len(scored) > 1 else -1.0
                if (
                    best_score >= self.minimum_similarity
                    and best_score - runner_up_score >= self.minimum_margin
                ):
                    results[result_index] = SkillMapping(
                        input_name=name,
                        standard_skill=best_skill,
                        method=SkillMappingMethod.VECTOR,
                        similarity=round(best_score, 6),
                    )

        return [result for result in results if result is not None]

    async def _get_catalog_vectors(self) -> list[list[float]]:
        if self._catalog_vectors is not None:
            return self._catalog_vectors
        async with self._catalog_lock:
            if self._catalog_vectors is None:
                self._catalog_vectors = await self.gateway.embed(
                    model=self.model,
                    texts=[_catalogue_description(skill) for skill in self.catalog.skills],
                    task="search_document",
                )
        return self._catalog_vectors


def _catalogue_description(skill: StandardSkill) -> str:
    aliases = ", ".join(skill.aliases)
    return f"Skill: {skill.preferred_label}. Also known as: {aliases}."


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Embedding vectors must have the same non-zero dimensions")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("Embedding vectors must not be zero vectors")
    return sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())
