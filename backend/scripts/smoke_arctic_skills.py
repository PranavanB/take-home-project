import asyncio
from pathlib import Path

from app.catalog import load_skill_catalog
from app.gateway import OpenAIEmbeddingGateway
from app.skill_mapper import _catalogue_description, _cosine_similarity

MODEL = "Snowflake/snowflake-arctic-embed-m-v2.0"
PHRASES = [
    "container orchestration platform",
    "building RESTful web services",
    "communicating with business leaders",
    "querying relational databases",
    "automated software delivery pipelines",
    "monitoring application logs",
    "analysing business data",
    "leading a team of engineers",
    "evaluating how components work together as a system",
    "planning and organising work",
    "spreadsheet expertise",
    "writing legal contracts",
]


async def main() -> None:
    root = Path(__file__).resolve().parents[2]
    catalog = load_skill_catalog(root / "seed" / "skills" / "skills.json")
    gateway = OpenAIEmbeddingGateway(
        base_url="http://127.0.0.1:8002/v1",
        model=MODEL,
    )
    document_vectors = await gateway.embed(
        model=MODEL,
        texts=[_catalogue_description(skill) for skill in catalog.skills],
        task="search_document",
    )
    query_vectors = await gateway.embed(
        model=MODEL,
        texts=PHRASES,
        task="search_query",
    )

    print(f"model={MODEL}")
    print(f"dimensions={len(document_vectors[0])}")
    for phrase, query_vector in zip(PHRASES, query_vectors, strict=True):
        ranked = sorted(
            (
                (_cosine_similarity(query_vector, vector), skill.preferred_label)
                for skill, vector in zip(
                    catalog.skills,
                    document_vectors,
                    strict=True,
                )
            ),
            reverse=True,
        )
        best, runner_up = ranked[:2]
        print(
            f"{phrase!r} -> {best[1]!r} score={best[0]:.4f} "
            f"runner_up={runner_up[1]!r} margin={best[0] - runner_up[0]:.4f}"
        )


if __name__ == "__main__":
    asyncio.run(main())
