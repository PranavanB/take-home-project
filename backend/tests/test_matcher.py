from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.catalog import load_industry_catalog, load_job_dataset, load_skill_catalog
from app.domain import (
    CandidateCountry,
    CandidateEducationLevel,
    CandidateExperience,
    CandidateIndustry,
    CandidateProfile,
    CandidateSkill,
    CandidateStandardSkill,
    EducationLevel,
    EvidenceReference,
    MatchCategory,
    RequirementStatus,
)
from app.matcher import CATEGORY_WEIGHTS, MatchAnalyzer

SEED_ROOT = Path(__file__).resolve().parents[2] / "seed"


def make_profile(
    *,
    standardized_skill_labels: list[str],
    education_level: EducationLevel = EducationLevel.BACHELORS,
    country_code: str | None = "GB",
    industry_code: str | None = "54",
    total_experience_months: int = 0,
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
    experience = (
        CandidateExperience(
            experience_id=uuid4(),
            title="Grounded role",
            company="Grounded employer",
            start_date="2024-01",
            end_date="2025-12",
            evidence=[reference],
        )
        if total_experience_months > 0
        else None
    )
    return CandidateProfile(
        profile_id=uuid4(),
        resume_id=uuid4(),
        extractor_version="test",
        experience_as_of=date(2026, 8, 26),
        total_experience_months=total_experience_months,
        featured_experience_id=experience.experience_id if experience else None,
        experiences=[experience] if experience else [],
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
    assert all(len(match.category_coverage) == 5 for match in first.top_matches)
    assert all(
        requirement.category
        in {
            MatchCategory.EDUCATION,
            MatchCategory.SKILLS,
            MatchCategory.EXPERIENCE,
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
    frontend_job = next(job for job in jobs if job.title == "Frontend Engineer")
    comparison_jobs = [frontend_job, *[job for job in jobs if job != frontend_job][:2]]

    results = await MatchAnalyzer(catalog, industries).analyze(
        profile=profile,
        jobs=comparison_jobs,
    )
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


@pytest.mark.asyncio
async def test_experience_duration_is_an_exact_ranked_requirement() -> None:
    jobs = load_job_dataset(SEED_ROOT / "jobs")
    target = next(job for job in jobs if job.title == "Cabin Crew – Talent Pool")
    comparison_jobs = [target, *[job for job in jobs if job != target][:2]]
    catalog = load_skill_catalog(SEED_ROOT / "skills" / "skills.json")
    industries = load_industry_catalog(SEED_ROOT / "industries" / "naics-2022.json")
    analyzer = MatchAnalyzer(catalog, industries)

    met_results = await analyzer.analyze(
        profile=make_profile(
            standardized_skill_labels=[],
            total_experience_months=12,
        ),
        jobs=comparison_jobs,
    )
    missing_results = await analyzer.analyze(
        profile=make_profile(
            standardized_skill_labels=[],
            total_experience_months=11,
        ),
        jobs=comparison_jobs,
    )

    met_job = next(match for match in met_results.top_matches if match.job_id == target.job_id)
    missing_job = next(
        match for match in missing_results.top_matches if match.job_id == target.job_id
    )
    met_requirement = next(
        item for item in met_job.requirements if item.category == MatchCategory.EXPERIENCE
    )
    missing_requirement = next(
        item for item in missing_job.requirements if item.category == MatchCategory.EXPERIENCE
    )
    assert met_requirement.status == RequirementStatus.MET
    assert missing_requirement.status == RequirementStatus.MISSING


@pytest.mark.asyncio
async def test_explicit_category_weights_drive_ranking_instead_of_raw_counts() -> None:
    jobs = load_job_dataset(SEED_ROOT / "jobs")
    catalog = load_skill_catalog(SEED_ROOT / "skills" / "skills.json")
    industries = load_industry_catalog(SEED_ROOT / "industries" / "naics-2022.json")
    by_label = {skill.preferred_label: skill.skill_id for skill in catalog.skills}
    profile = make_profile(
        standardized_skill_labels=["Python (computer programming)"],
        total_experience_months=24,
    )
    base = jobs[0]
    aligned = base.model_copy(
        update={
            "job_id": UUID("00000000-0000-4000-8000-000000000001"),
            "title": "Zulu aligned role",
            "required_skill_ids": [
                by_label["Python (computer programming)"],
                by_label["SQL"],
                by_label["Docker"],
                by_label["PostgreSQL"],
                by_label["cloud technologies"],
            ],
            "preferred_skill_ids": [],
            "minimum_experience_months": 24,
        }
    )
    skills_only = base.model_copy(
        update={
            "job_id": UUID("00000000-0000-4000-8000-000000000002"),
            "title": "Alpha skills-only role",
            "required_skill_ids": [by_label["Python (computer programming)"]],
            "preferred_skill_ids": [],
            "minimum_education_level": EducationLevel.MASTERS,
            "minimum_experience_months": 36,
            "country_code": "US",
            "industry_id": next(
                item.industry_id for item in industries.industries if item.naics_code == "44-45"
            ),
        }
    )
    third = skills_only.model_copy(
        update={
            "job_id": UUID("00000000-0000-4000-8000-000000000003"),
            "required_skill_ids": [],
        }
    )

    results = await MatchAnalyzer(catalog, industries).analyze(
        profile=profile,
        jobs=[skills_only, aligned, third],
    )

    assert CATEGORY_WEIGHTS == {
        MatchCategory.SKILLS: 40,
        MatchCategory.EXPERIENCE: 25,
        MatchCategory.EDUCATION: 15,
        MatchCategory.LOCATION: 10,
        MatchCategory.INDUSTRY: 10,
    }
    assert results.top_matches[0].job_id == aligned.job_id
    assert results.top_matches[0].required_rank_score > results.top_matches[1].required_rank_score


@pytest.mark.asyncio
async def test_job_titles_do_not_break_ranking_ties() -> None:
    jobs = load_job_dataset(SEED_ROOT / "jobs")
    catalog = load_skill_catalog(SEED_ROOT / "skills" / "skills.json")
    industries = load_industry_catalog(SEED_ROOT / "industries" / "naics-2022.json")
    base = jobs[0]
    tied_jobs = [
        base.model_copy(
            update={
                "job_id": UUID("00000000-0000-4000-8000-000000000002"),
                "title": "Alpha role",
            }
        ),
        base.model_copy(
            update={
                "job_id": UUID("00000000-0000-4000-8000-000000000001"),
                "title": "Zulu role",
            }
        ),
        base.model_copy(
            update={
                "job_id": UUID("00000000-0000-4000-8000-000000000003"),
                "title": "Middle role",
            }
        ),
    ]

    results = await MatchAnalyzer(catalog, industries).analyze(
        profile=make_profile(standardized_skill_labels=[]),
        jobs=tied_jobs,
    )

    assert [match.title for match in results.top_matches] == [
        "Zulu role",
        "Alpha role",
        "Middle role",
    ]
