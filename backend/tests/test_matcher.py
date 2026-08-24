from pathlib import Path
from uuid import uuid4

import pytest

from app.catalog import load_industry_catalog, load_job_dataset, load_skill_catalog
from app.domain import (
    CandidateCountry,
    CandidateEducationLevel,
    CandidateIndustry,
    CandidateProfile,
    CandidateSkill,
    CandidateStandardSkill,
    EducationLevel,
    EvidenceReference,
    MatchCategory,
    RequirementStatus,
)
from app.matcher import MatchAnalyzer

SEED_ROOT = Path(__file__).resolve().parents[2] / "seed"


def make_profile(
    *,
    standardized_skill_labels: list[str],
    education_level: EducationLevel = EducationLevel.BACHELORS,
    country_code: str | None = "GB",
    industry_code: str | None = "54",
) -> CandidateProfile:
    catalog = load_skill_catalog(SEED_ROOT / "skills" / "skills.json")
    industries = load_industry_catalog(SEED_ROOT / "industries" / "naics-2022.json")
    by_label = {skill.preferred_label: skill for skill in catalog.skills}
    block_id = uuid4()
    reference = EvidenceReference(block_id=block_id, quote="Grounded CV evidence")
    standardized = [
        CandidateStandardSkill(
            candidate_standard_skill_id=uuid4(),
            standard_skill_id=by_label[label].skill_id,
            preferred_label=label,
            source=by_label[label].source,
            evidence=[reference],
        )
        for label in standardized_skill_labels
    ]
    return CandidateProfile(
        profile_id=uuid4(),
        resume_id=uuid4(),
        extractor_version="test",
        featured_experience_id=None,
        experiences=[],
        skills=[
            CandidateSkill(
                skill_id=uuid4(),
                name="Python",
                evidence=[reference],
            )
        ],
        standardized_skills=standardized,
        education_level=CandidateEducationLevel(
            education_level_id=uuid4(),
            level=education_level,
            eqf_level=education_level.eqf_level,
            evidence=[reference],
        ),
        country=(
            CandidateCountry(
                country_id=uuid4(),
                country_code=country_code,
                name="United Kingdom",
                evidence=[reference],
            )
            if country_code
            else None
        ),
        industry=(
            CandidateIndustry(
                candidate_industry_id=uuid4(),
                industry_id=next(
                    item.industry_id
                    for item in industries.industries
                    if item.naics_code == industry_code
                ),
                naics_code=industry_code,
                preferred_label=next(
                    item.preferred_label
                    for item in industries.industries
                    if item.naics_code == industry_code
                ),
                evidence=[reference],
            )
            if industry_code
            else None
        ),
        qualifications=[],
        education=[],
    )


@pytest.mark.asyncio
async def test_database_match_returns_stable_top_three() -> None:
    jobs = load_job_dataset(SEED_ROOT / "jobs")
    catalog = load_skill_catalog(SEED_ROOT / "skills" / "skills.json")
    industries = load_industry_catalog(SEED_ROOT / "industries" / "naics-2022.json")
    profile = make_profile(
        standardized_skill_labels=[
            "Python (computer programming)",
            "SQL",
            "Docker",
            "PostgreSQL",
            "cloud technologies",
        ]
    )
    analyzer = MatchAnalyzer(catalog, industries)

    first = await analyzer.analyze(profile=profile, jobs=jobs)
    second = await analyzer.analyze(profile=profile, jobs=jobs)

    assert first == second
    assert len(first.top_matches) == 3
    assert first.top_matches[0].title == "Senior Backend Engineer"
    assert all(len(match.category_coverage) == 4 for match in first.top_matches)
    assert all(
        requirement.category
        in {
            MatchCategory.EDUCATION,
            MatchCategory.SKILLS,
            MatchCategory.LOCATION,
            MatchCategory.INDUSTRY,
        }
        for match in first.top_matches
        for requirement in match.requirements
    )
    assert all(
        requirement.status in {RequirementStatus.MET, RequirementStatus.MISSING}
        for match in first.top_matches
        for requirement in match.requirements
    )


@pytest.mark.asyncio
async def test_only_standard_skill_ids_match() -> None:
    jobs = load_job_dataset(SEED_ROOT / "jobs")
    backend_job = next(job for job in jobs if job.title == "Senior Backend Engineer")
    comparison_jobs = [backend_job, *[job for job in jobs if job != backend_job][:2]]
    catalog = load_skill_catalog(SEED_ROOT / "skills" / "skills.json")
    industries = load_industry_catalog(SEED_ROOT / "industries" / "naics-2022.json")
    profile = make_profile(standardized_skill_labels=[], industry_code=None)

    results = await MatchAnalyzer(catalog, industries).analyze(
        profile=profile,
        jobs=comparison_jobs,
    )
    backend = next(
        match for match in results.top_matches if match.title == "Senior Backend Engineer"
    )
    python_requirement = next(
        item for item in backend.requirements if item.text == "Python (computer programming)"
    )

    assert profile.skills[0].name == "Python"
    assert python_requirement.status == RequirementStatus.MISSING
    assert python_requirement.evidence == []


@pytest.mark.asyncio
async def test_higher_education_level_satisfies_lower_minimum() -> None:
    jobs = load_job_dataset(SEED_ROOT / "jobs")
    catalog = load_skill_catalog(SEED_ROOT / "skills" / "skills.json")
    industries = load_industry_catalog(SEED_ROOT / "industries" / "naics-2022.json")
    profile = make_profile(
        standardized_skill_labels=[],
        education_level=EducationLevel.MASTERS,
        industry_code=None,
    )

    results = await MatchAnalyzer(catalog, industries).analyze(profile=profile, jobs=jobs)
    frontend = next(
        match for match in results.top_matches if match.title == "Frontend Engineer"
    )
    education = next(
        item for item in frontend.requirements if item.category == MatchCategory.EDUCATION
    )

    assert education.status == RequirementStatus.MET
    assert education.evidence


@pytest.mark.asyncio
async def test_country_uses_exact_iso_code_match() -> None:
    jobs = load_job_dataset(SEED_ROOT / "jobs")
    catalog = load_skill_catalog(SEED_ROOT / "skills" / "skills.json")
    industries = load_industry_catalog(SEED_ROOT / "industries" / "naics-2022.json")
    profile = make_profile(standardized_skill_labels=[], country_code=None)

    results = await MatchAnalyzer(catalog, industries).analyze(profile=profile, jobs=jobs)

    assert all(
        requirement.status == RequirementStatus.MISSING
        for match in results.top_matches
        for requirement in match.requirements
        if requirement.category == MatchCategory.LOCATION
    )


@pytest.mark.asyncio
async def test_industry_uses_exact_naics_sector_match() -> None:
    jobs = load_job_dataset(SEED_ROOT / "jobs")
    catalog = load_skill_catalog(SEED_ROOT / "skills" / "skills.json")
    industries = load_industry_catalog(SEED_ROOT / "industries" / "naics-2022.json")
    profile = make_profile(standardized_skill_labels=[], industry_code=None)

    results = await MatchAnalyzer(catalog, industries).analyze(profile=profile, jobs=jobs)

    assert all(
        requirement.status == RequirementStatus.MISSING
        for match in results.top_matches
        for requirement in match.requirements
        if requirement.category == MatchCategory.INDUSTRY
    )
