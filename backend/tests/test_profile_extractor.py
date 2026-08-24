from pathlib import Path
from typing import Any
from uuid import uuid4, uuid5

import pytest
from pydantic import ValidationError

from app.catalog import load_industry_catalog, load_skill_catalog
from app.domain import (
    DocumentType,
    EducationLevel,
    ExtractedBlock,
    ExtractedDocument,
    SkillMappingMethod,
)
from app.profile_extractor import (
    ProfileExtractor,
    _canonical_source_excerpt,
    build_category_schema,
    build_user_prompt,
)
from app.skill_mapper import SkillVectorMapper


class FakeGenerator:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.system_prompt = ""
        self.user_prompt = ""
        self.json_schema: dict[str, Any] = {}
        self.schemas: list[dict[str, Any]] = []

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.json_schema = json_schema
        self.schemas.append(json_schema)
        return self.response


class ProfileEmbeddingGateway:
    async def embed(
        self,
        *,
        model: str,
        texts: list[str],
        task: str,
    ) -> list[list[float]]:
        return [
            [1.0, 0.0] if "kubernetes" in text.casefold() else [-1.0, 0.0]
            for text in texts
        ]


def make_document() -> ExtractedDocument:
    resume_id = uuid4()
    first_id = uuid5(resume_id, "block:1")
    second_id = uuid5(resume_id, "block:2")
    return ExtractedDocument(
        reader_version="test-reader",
        resume_id=resume_id,
        document_type=DocumentType.PDF,
        page_count=2,
        char_count=400,
        blocks=[
            ExtractedBlock(
                block_id=first_id,
                ordinal=1,
                source_label="Page 1",
                page_number=1,
                kind="page",
                text=(
                    "Software Engineer - Elm Digital, 2018-06 to 2021-12. "
                    "Developed Python and TypeScript applications."
                ),
            ),
            ExtractedBlock(
                block_id=second_id,
                ordinal=2,
                source_label="Page 2",
                page_number=2,
                kind="page",
                text=(
                    "Senior Software Engineer - Cedar Systems, 2022-01 to Present. "
                    "Built FastAPI services. Skills: Python, FastAPI, Systems Analysis. "
                    "Industry: Professional, Scientific, and Technical Services. "
                    "BSc Computer Science - Northbridge University, 2018. "
                    "AWS Certified Developer - Associate."
                ),
            ),
        ],
    )


def test_experience_request_uses_bounded_concise_contract() -> None:
    document = make_document()
    prompt = build_user_prompt(document, category="experiences")
    schema = build_category_schema("experiences")

    assert "Set highlights to an empty array" in prompt
    assert schema["properties"]["experiences"]["maxItems"] == 20
    assert (
        schema["$defs"]["ExperienceDraft"]["properties"]["highlights"]["maxItems"]
        == 0
    )
    assert schema["$defs"]["ExperienceDraft"]["properties"]["evidence"]["maxItems"] == 1
    assert schema["$defs"]["EvidenceReference"]["properties"]["quote"]["maxLength"] == 240


def test_repairs_only_formatting_differences_with_exact_source_excerpt() -> None:
    source = "Led cloud-first delivery — across teams."

    assert _canonical_source_excerpt(
        source,
        "Led cloud first delivery across teams",
    ) == "Led cloud-first delivery — across teams"
    assert _canonical_source_excerpt(source, "Managed cloud delivery") is None


def valid_response(document: ExtractedDocument) -> dict[str, Any]:
    old_block = str(document.blocks[0].block_id)
    current_block = str(document.blocks[1].block_id)
    return {
        "experiences": [
            {
                "title": "Software Engineer",
                "company": "Elm Digital",
                "start_date": "2018-06",
                "end_date": "2021-12",
                "is_current": False,
                "highlights": [
                    {
                        "text": "Developed Python and TypeScript applications.",
                        "evidence": [
                            {
                                "block_id": old_block,
                                "quote": "Developed Python and TypeScript applications.",
                            }
                        ],
                    }
                ],
                "evidence": [
                    {
                        "block_id": old_block,
                        "quote": "Software Engineer - Elm Digital, 2018-06 to 2021-12",
                    }
                ],
            },
            {
                "title": "Senior Software Engineer",
                "company": "Cedar Systems",
                "start_date": "2022-01",
                "end_date": None,
                "is_current": True,
                "highlights": [],
                "evidence": [
                    {
                        "block_id": current_block,
                        "quote": (
                            "Senior Software Engineer - Cedar Systems, "
                            "2022-01 to Present"
                        ),
                    }
                ],
            },
        ],
        "skills": [
            {
                "name": "Python",
                "evidence": [
                    {"block_id": current_block, "quote": "Skills: Python, FastAPI"}
                ],
            },
            {
                "name": "python",
                "evidence": [
                    {
                        "block_id": old_block,
                        "quote": "Developed Python and TypeScript applications.",
                    }
                ],
            },
            {
                "name": "Systems Analysis",
                "evidence": [
                    {
                        "block_id": current_block,
                        "quote": "Skills: Python, FastAPI, Systems Analysis",
                    }
                ],
            },
        ],
        "qualifications": [
            {
                "name": "AWS Certified Developer - Associate",
                "kind": "certification",
                "issuer": "AWS",
                "awarded_date": None,
                "evidence": [
                    {
                        "block_id": current_block,
                        "quote": "AWS Certified Developer - Associate",
                    }
                ],
            }
        ],
        "education": [
            {
                "degree": "BSc Computer Science",
                "institution": "Northbridge University",
                "field_of_study": "Computer Science",
                "start_date": None,
                "end_date": "2018",
                "evidence": [
                    {
                        "block_id": current_block,
                        "quote": (
                            "BSc Computer Science - Northbridge University, 2018"
                        ),
                    }
                ],
            }
        ],
        "country": {
            "country_code": "GB",
            "name": "United Kingdom",
            "evidence": [
                {
                    "block_id": current_block,
                    "quote": "Cedar Systems",
                }
            ],
        },
        "industry": {
            "name": "Professional, Scientific, and Technical Services",
            "evidence": [
                {
                    "block_id": current_block,
                    "quote": (
                        "Industry: Professional, Scientific, and Technical Services"
                    ),
                }
            ],
        },
    }


@pytest.mark.asyncio
async def test_extracts_grounded_profile_with_current_role_first_and_stable_ids() -> None:
    document = make_document()
    generator = FakeGenerator(valid_response(document))
    skill_catalog = load_skill_catalog(
        Path(__file__).resolve().parents[2] / "seed" / "skills" / "skills.json"
    )
    industry_catalog = load_industry_catalog(
        Path(__file__).resolve().parents[2]
        / "seed"
        / "industries"
        / "naics-2022.json"
    )
    extractor = ProfileExtractor(generator, skill_catalog, industry_catalog)

    first = await extractor.extract(document)
    second = await extractor.extract(document)

    assert first == second
    assert first.profile_id.version == 5
    assert first.experiences[0].company == "Cedar Systems"
    assert first.featured_experience_id == first.experiences[0].experience_id
    assert len(first.skills) == 2
    assert len(first.skills[0].evidence) == 2
    assert first.education[0].degree == "BSc Computer Science"
    assert first.qualifications[0].name.startswith("AWS Certified")
    assert first.education_level.level == EducationLevel.BACHELORS
    assert first.education_level.eqf_level == 6
    assert first.country is not None
    assert first.country.country_code == "GB"
    assert first.industry is not None
    assert first.industry.naics_code == "54"
    assert [skill.preferred_label for skill in first.standardized_skills] == [
        "Python (computer programming)",
        "Systems Analysis",
    ]
    assert first.standardized_skills[1].source.value == "onet"
    assert "untrusted" in generator.system_prompt.casefold()
    assert str(document.blocks[0].block_id) in generator.user_prompt
    assert len(generator.schemas) == 12
    expected_categories = [
        "experiences",
        "skills",
        "qualifications",
        "education",
        "country",
        "industry",
    ]
    assert [next(iter(schema["properties"])) for schema in generator.schemas] == (
        expected_categories * 2
    )
    assert all(schema["additionalProperties"] is False for schema in generator.schemas)


@pytest.mark.asyncio
async def test_recovers_explicit_labelled_industry_when_model_omits_it() -> None:
    document = make_document()
    response = valid_response(document)
    response["industry"] = None
    industry_catalog = load_industry_catalog(
        Path(__file__).resolve().parents[2]
        / "seed"
        / "industries"
        / "naics-2022.json"
    )

    profile = await ProfileExtractor(
        FakeGenerator(response),
        industry_catalog=industry_catalog,
    ).extract(document)

    assert profile.industry is not None
    assert profile.industry.naics_code == "54"
    assert profile.industry.evidence[0].quote == (
        "Industry: Professional, Scientific, and Technical Services"
    )


@pytest.mark.asyncio
async def test_profile_keeps_all_llm_skills_and_vector_maps_supported_wording() -> None:
    document = make_document()
    document.blocks[1].text += (
        " Led a Kubernetes platform in production and used an "
        "Uncatalogued specialist technique."
    )
    response = valid_response(document)
    response["skills"] = [
        {
            "name": "Kubernetes platform",
            "evidence": [
                {
                    "block_id": str(document.blocks[1].block_id),
                    "quote": "Kubernetes platform in production",
                }
            ],
        },
        {
            "name": "Uncatalogued specialist technique",
            "evidence": [
                {
                    "block_id": str(document.blocks[1].block_id),
                    "quote": "Uncatalogued specialist technique",
                }
            ],
        },
    ]
    catalog = load_skill_catalog(
        Path(__file__).resolve().parents[2] / "seed" / "skills" / "skills.json"
    )
    mapper = SkillVectorMapper(
        catalog=catalog,
        gateway=ProfileEmbeddingGateway(),
        model="test-embedding",
        minimum_similarity=0.75,
        minimum_margin=0.05,
    )

    profile = await ProfileExtractor(
        FakeGenerator(response),
        skill_catalog=catalog,
        skill_mapper=mapper,
    ).extract(document)

    assert {skill.name for skill in profile.skills} == {
        "Kubernetes platform",
        "Uncatalogued specialist technique",
    }
    assert [skill.preferred_label for skill in profile.standardized_skills] == [
        "Kubernetes"
    ]
    assert profile.standardized_skills[0].mapping_method == SkillMappingMethod.VECTOR


@pytest.mark.asyncio
async def test_replaces_model_quote_with_exact_source_evidence() -> None:
    document = make_document()
    response = valid_response(document)
    response["skills"][0]["evidence"][0]["quote"] = "Ten years of Kubernetes"

    profile = await ProfileExtractor(FakeGenerator(response)).extract(document)

    assert profile.skills[0].evidence[0].quote in document.combined_text()
    assert profile.skills[0].evidence[0].quote != "Ten years of Kubernetes"


@pytest.mark.asyncio
async def test_drops_profile_item_not_present_in_document() -> None:
    document = make_document()
    response = valid_response(document)
    response["skills"][0]["name"] = "Kubernetes"

    profile = await ProfileExtractor(FakeGenerator(response)).extract(document)

    assert all(skill.name != "Kubernetes" for skill in profile.skills)


@pytest.mark.asyncio
async def test_replaces_unknown_model_block_with_exact_source_block() -> None:
    document = make_document()
    response = valid_response(document)
    response["skills"][0]["evidence"][0]["block_id"] = str(uuid4())

    profile = await ProfileExtractor(FakeGenerator(response)).extract(document)

    assert profile.skills[0].evidence[0].block_id in {
        block.block_id for block in document.blocks
    }


@pytest.mark.asyncio
async def test_rejects_degree_misclassified_as_qualification() -> None:
    document = make_document()
    response = valid_response(document)
    response["qualifications"][0]["name"] = "MSc Data Science"

    with pytest.raises(ValidationError, match="Degrees belong under education"):
        await ProfileExtractor(FakeGenerator(response)).extract(document)


@pytest.mark.asyncio
async def test_rejects_non_normalised_date() -> None:
    document = make_document()
    response = valid_response(document)
    response["experiences"][0]["start_date"] = "June 2018"

    with pytest.raises(ValidationError, match="string_pattern_mismatch"):
        await ProfileExtractor(FakeGenerator(response)).extract(document)
