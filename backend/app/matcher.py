import sqlite3
from collections.abc import Iterable
from fractions import Fraction
from uuid import UUID, uuid5

from app.domain import (
    CandidateEvidence,
    CandidateProfile,
    CategoryCoverage,
    EducationLevel,
    IndustryCatalog,
    JobFixture,
    JobMatch,
    JobRequirement,
    MatchCategory,
    MatchResults,
    RequirementImportance,
    RequirementMatch,
    RequirementStatus,
    SkillCatalog,
)

MATCHER_VERSION = "exact-database-matcher-v4"
CATEGORY_WEIGHTS = {
    MatchCategory.SKILLS: 40,
    MatchCategory.EXPERIENCE: 25,
    MatchCategory.EDUCATION: 15,
    MatchCategory.LOCATION: 10,
    MatchCategory.INDUSTRY: 10,
}


class MatchAnalyzer:
    def __init__(
        self,
        skill_catalog: SkillCatalog,
        industry_catalog: IndustryCatalog,
    ) -> None:
        self.skill_catalog = skill_catalog
        self.industry_catalog = industry_catalog

    async def analyze(
        self,
        *,
        profile: CandidateProfile,
        jobs: list[JobFixture],
    ) -> MatchResults:
        requirements_version = validate_job_versions(
            jobs,
            skill_catalog_version=self.skill_catalog.version,
            industry_catalog_version=self.industry_catalog.version,
        )
        evidence, candidate_facts = build_candidate_facts(profile)
        analysis_id = uuid5(
            profile.profile_id,
            f"{MATCHER_VERSION}:{requirements_version}:analysis",
        )
        matches = [
            self._analyze_job(
                analysis_id=analysis_id,
                profile=profile,
                job=job,
                evidence=evidence,
                candidate_facts=candidate_facts,
            )
            for job in jobs
        ]
        ranked = sorted(
            matches,
            key=lambda match: (
                -match.required_rank_score,
                -match.preferred_rank_score,
                str(match.job_id),
            ),
        )
        return MatchResults(
            analysis_id=analysis_id,
            profile_id=profile.profile_id,
            matcher_version=MATCHER_VERSION,
            job_requirements_version=requirements_version,
            top_matches=ranked[:3],
        )

    def _analyze_job(
        self,
        *,
        analysis_id: UUID,
        profile: CandidateProfile,
        job: JobFixture,
        evidence: dict[UUID, CandidateEvidence],
        candidate_facts: dict[str, UUID],
    ) -> JobMatch:
        requirements = build_job_requirements(
            job,
            self.skill_catalog,
            self.industry_catalog,
        )
        joined = exact_database_join(requirements, candidate_facts)
        resolved = [
            resolve_requirement(
                requirement,
                evidence.get(joined[requirement.requirement_id]),
                profile,
            )
            for requirement in requirements
        ]
        required = [
            item for item in resolved if item.importance == RequirementImportance.REQUIRED
        ]
        preferred = [
            item for item in resolved if item.importance == RequirementImportance.PREFERRED
        ]
        return JobMatch(
            match_result_id=uuid5(analysis_id, f"job:{job.job_id}"),
            job_id=job.job_id,
            title=job.title,
            company=job.company,
            summary=job.summary,
            required_coverage_points=sum(
                item.status == RequirementStatus.MET for item in required
            ),
            required_coverage_max=len(required),
            preferred_coverage_points=sum(
                item.status == RequirementStatus.MET for item in preferred
            ),
            preferred_coverage_max=len(preferred),
            required_rank_score=weighted_rank_score(
                resolved,
                RequirementImportance.REQUIRED,
            ),
            preferred_rank_score=weighted_rank_score(
                resolved,
                RequirementImportance.PREFERRED,
            ),
            category_coverage=build_category_coverage(resolved),
            requirements=resolved,
        )


def build_job_requirements(
    job: JobFixture,
    skill_catalog: SkillCatalog,
    industry_catalog: IndustryCatalog,
) -> list[JobRequirement]:
    skills_by_id = {skill.skill_id: skill for skill in skill_catalog.skills}
    industries_by_id = {
        industry.industry_id: industry for industry in industry_catalog.industries
    }
    requirements: list[JobRequirement] = []

    def append_requirement(
        *,
        text: str,
        importance: RequirementImportance,
        category: MatchCategory,
        standard_key: str,
    ) -> None:
        ordinal = len(requirements) + 1
        requirements.append(
            JobRequirement(
                requirement_id=uuid5(
                    job.job_id,
                    f"{MATCHER_VERSION}:{job.requirements_version}:{importance}:{standard_key}",
                ),
                text=text,
                importance=importance,
                category=category,
                standard_key=standard_key,
                ordinal=ordinal,
            )
        )

    if job.minimum_education_level is not None:
        append_requirement(
            text=f"At least {job.minimum_education_level.display_name}",
            importance=RequirementImportance.REQUIRED,
            category=MatchCategory.EDUCATION,
            standard_key=education_key(job.minimum_education_level),
        )
    for skill_id in job.required_skill_ids:
        skill = skills_by_id[skill_id]
        append_requirement(
            text=skill.preferred_label,
            importance=RequirementImportance.REQUIRED,
            category=MatchCategory.SKILLS,
            standard_key=skill_key(skill_id),
        )
    if job.minimum_experience_months is not None:
        append_requirement(
            text=f"At least {format_experience(job.minimum_experience_months)} of experience",
            importance=RequirementImportance.REQUIRED,
            category=MatchCategory.EXPERIENCE,
            standard_key=experience_key(job.minimum_experience_months),
        )
    append_requirement(
        text=f"Located in {job.country_code}",
        importance=RequirementImportance.REQUIRED,
        category=MatchCategory.LOCATION,
        standard_key=country_key(job.country_code),
    )
    industry = industries_by_id[job.industry_id]
    append_requirement(
        text=industry.preferred_label,
        importance=RequirementImportance.REQUIRED,
        category=MatchCategory.INDUSTRY,
        standard_key=industry_key(industry.industry_id),
    )
    for skill_id in job.preferred_skill_ids:
        skill = skills_by_id[skill_id]
        append_requirement(
            text=skill.preferred_label,
            importance=RequirementImportance.PREFERRED,
            category=MatchCategory.SKILLS,
            standard_key=skill_key(skill_id),
        )
    return requirements


def build_candidate_facts(
    profile: CandidateProfile,
) -> tuple[dict[UUID, CandidateEvidence], dict[str, UUID]]:
    evidence: dict[UUID, CandidateEvidence] = {}
    facts: dict[str, UUID] = {}
    for skill in profile.standardized_skills:
        evidence_id = uuid5(
            profile.profile_id,
            f"{MATCHER_VERSION}:skill:{skill.standard_skill_id}",
        )
        item = CandidateEvidence(
            evidence_id=evidence_id,
            category=MatchCategory.SKILLS,
            standard_key=skill_key(skill.standard_skill_id),
            label=skill.preferred_label,
            references=skill.evidence[:3],
        )
        evidence[evidence_id] = item
        facts[item.standard_key] = evidence_id

    if profile.education_level is not None:
        level = profile.education_level.level
        evidence_id = uuid5(
            profile.profile_id,
            f"{MATCHER_VERSION}:education:{level}",
        )
        item = CandidateEvidence(
            evidence_id=evidence_id,
            category=MatchCategory.EDUCATION,
            standard_key=education_key(level),
            label=f"{level.display_name} · EQF {level.eqf_level}",
            references=profile.education_level.evidence[:3],
        )
        evidence[evidence_id] = item
        for accepted_level in EducationLevel:
            if accepted_level.eqf_level <= level.eqf_level:
                facts[education_key(accepted_level)] = evidence_id

    if profile.country is not None:
        evidence_id = uuid5(
            profile.profile_id,
            f"{MATCHER_VERSION}:country:{profile.country.country_code}",
        )
        item = CandidateEvidence(
            evidence_id=evidence_id,
            category=MatchCategory.LOCATION,
            standard_key=country_key(profile.country.country_code),
            label=f"{profile.country.name} ({profile.country.country_code})",
            references=profile.country.evidence[:3],
        )
        evidence[evidence_id] = item
        facts[item.standard_key] = evidence_id

    if profile.total_experience_months > 0:
        references = [
            reference
            for experience in profile.experiences
            if experience.start_date is not None
            for reference in experience.evidence
        ][:3]
        if references:
            evidence_id = uuid5(
                profile.profile_id,
                f"{MATCHER_VERSION}:experience:{profile.total_experience_months}",
            )
            item = CandidateEvidence(
                evidence_id=evidence_id,
                category=MatchCategory.EXPERIENCE,
                standard_key=experience_key(profile.total_experience_months),
                label=(
                    f"{format_experience(profile.total_experience_months)} across dated CV roles "
                    f"(as of {profile.experience_as_of.isoformat()})"
                ),
                references=references,
            )
            evidence[evidence_id] = item
            for accepted_months in range(1, profile.total_experience_months + 1):
                facts[experience_key(accepted_months)] = evidence_id

    if profile.industry is not None:
        evidence_id = uuid5(
            profile.profile_id,
            f"{MATCHER_VERSION}:industry:{profile.industry.industry_id}",
        )
        item = CandidateEvidence(
            evidence_id=evidence_id,
            category=MatchCategory.INDUSTRY,
            standard_key=industry_key(profile.industry.industry_id),
            label=(
                f"{profile.industry.preferred_label} "
                f"(NAICS {profile.industry.naics_code})"
            ),
            references=profile.industry.evidence[:3],
        )
        evidence[evidence_id] = item
        facts[item.standard_key] = evidence_id
    return evidence, facts


def exact_database_join(
    requirements: list[JobRequirement],
    candidate_facts: dict[str, UUID],
) -> dict[UUID, UUID | None]:
    database = sqlite3.connect(":memory:")
    try:
        database.execute(
            "CREATE TABLE requirement (requirement_id TEXT PRIMARY KEY, standard_key TEXT)"
        )
        database.execute(
            "CREATE TABLE candidate_fact (standard_key TEXT PRIMARY KEY, evidence_id TEXT)"
        )
        database.executemany(
            "INSERT INTO requirement VALUES (?, ?)",
            [(str(item.requirement_id), item.standard_key) for item in requirements],
        )
        database.executemany(
            "INSERT INTO candidate_fact VALUES (?, ?)",
            [(key, str(evidence_id)) for key, evidence_id in candidate_facts.items()],
        )
        rows = database.execute(
            """
            SELECT requirement.requirement_id, candidate_fact.evidence_id
            FROM requirement
            LEFT JOIN candidate_fact USING (standard_key)
            """
        ).fetchall()
        return {
            UUID(requirement_id): UUID(evidence_id) if evidence_id else None
            for requirement_id, evidence_id in rows
        }
    finally:
        database.close()


def resolve_requirement(
    requirement: JobRequirement,
    evidence: CandidateEvidence | None,
    profile: CandidateProfile,
) -> RequirementMatch:
    if evidence is not None:
        if requirement.category == MatchCategory.EDUCATION:
            explanation = f"{evidence.label} meets this minimum education level."
        elif requirement.category == MatchCategory.EXPERIENCE:
            explanation = f"{evidence.label} meets this minimum experience duration."
        elif requirement.category == MatchCategory.LOCATION:
            explanation = "The CV and job use the same ISO country code."
        elif requirement.category == MatchCategory.INDUSTRY:
            explanation = "The CV and job use the same NAICS industry UUID."
        else:
            explanation = "The standardized skill UUID is an exact match."
        return RequirementMatch(
            **requirement.model_dump(),
            status=RequirementStatus.MET,
            evidence=[evidence],
            explanation=explanation,
            action=None,
        )

    if requirement.category == MatchCategory.EDUCATION:
        explanation = "The CV does not show an education level that meets this minimum."
        action = f"Add truthful CV evidence of {requirement.text.casefold()} if applicable."
    elif requirement.category == MatchCategory.EXPERIENCE:
        explanation = (
            f"The dated CV roles total {format_experience(profile.total_experience_months)}, "
            "which does not meet this minimum."
        )
        action = "Make the start and end dates of relevant roles clear on your CV."
    elif requirement.category == MatchCategory.LOCATION:
        candidate_country = profile.country.country_code if profile.country else "not stated"
        explanation = f"The CV country ({candidate_country}) is not an exact ISO-code match."
        action = "Add your current country to the CV if it is accurate and relevant."
    elif requirement.category == MatchCategory.INDUSTRY:
        candidate_industry = (
            profile.industry.preferred_label if profile.industry else "not stated"
        )
        explanation = (
            f"The CV industry ({candidate_industry}) is not an exact NAICS-sector match."
        )
        action = "State your current industry on the CV if it is accurate and relevant."
    else:
        explanation = "No identical standardized skill UUID was found in the CV profile."
        action = f"Add truthful CV evidence for {requirement.text} if you have this skill."
    return RequirementMatch(
        **requirement.model_dump(),
        status=RequirementStatus.MISSING,
        evidence=[],
        explanation=explanation,
        action=action,
    )


def build_category_coverage(
    requirements: Iterable[RequirementMatch],
) -> list[CategoryCoverage]:
    items = list(requirements)
    return [
        CategoryCoverage(
            category=category,
            weight_percent=CATEGORY_WEIGHTS[category],
            coverage_percent=(
                round(
                    100
                    * sum(
                        item.category == category
                        and item.status == RequirementStatus.MET
                        for item in items
                    )
                    / sum(item.category == category for item in items)
                )
                if any(item.category == category for item in items)
                else 0
            ),
            met=sum(
                item.category == category and item.status == RequirementStatus.MET
                for item in items
            ),
            missing=sum(
                item.category == category and item.status == RequirementStatus.MISSING
                for item in items
            ),
        )
        for category in MatchCategory
    ]


def weighted_rank_score(
    requirements: Iterable[RequirementMatch],
    importance: RequirementImportance,
) -> int:
    items = [item for item in requirements if item.importance == importance]
    applicable_weight = 0
    weighted_coverage = Fraction(0)
    for category, weight in CATEGORY_WEIGHTS.items():
        category_items = [item for item in items if item.category == category]
        if not category_items:
            continue
        applicable_weight += weight
        met = sum(item.status == RequirementStatus.MET for item in category_items)
        weighted_coverage += Fraction(met, len(category_items)) * weight
    if applicable_weight == 0:
        return 0
    score = weighted_coverage / applicable_weight * 10_000
    return int(score + Fraction(1, 2))


def validate_job_versions(
    jobs: list[JobFixture],
    *,
    skill_catalog_version: str,
    industry_catalog_version: str,
) -> str:
    versions = {job.requirements_version for job in jobs}
    if len(versions) != 1:
        raise ValueError("All matched jobs must use one requirements version")
    if any(job.skill_catalog_version != skill_catalog_version for job in jobs):
        raise ValueError("Job and runtime skill catalog versions do not match")
    if any(job.industry_catalog_version != industry_catalog_version for job in jobs):
        raise ValueError("Job and runtime industry catalog versions do not match")
    return versions.pop()


def skill_key(skill_id: UUID) -> str:
    return f"skill:{skill_id}"


def education_key(level: EducationLevel) -> str:
    return f"education:{level}"


def experience_key(months: int) -> str:
    return f"experience-months:{months}"


def format_experience(months: int) -> str:
    years, remainder = divmod(months, 12)
    if years and remainder:
        year_label = f"{years} year{'s' if years != 1 else ''}"
        month_label = f"{remainder} month{'s' if remainder != 1 else ''}"
        return f"{year_label} {month_label}"
    if years:
        return f"{years} year{'s' if years != 1 else ''}"
    return f"{months} month{'s' if months != 1 else ''}"


def country_key(country_code: str) -> str:
    return f"country:{country_code.upper()}"


def industry_key(industry_id: UUID) -> str:
    return f"industry:{industry_id}"
