from pathlib import Path

from app.catalog import load_industry_catalog, load_job_dataset, load_skill_catalog
from app.domain import SkillSource


def test_standard_dataset_has_sixteen_unique_jobs_including_ten_sourced_roles() -> None:
    seed_root = Path(__file__).resolve().parents[2] / "seed"
    jobs = load_job_dataset(seed_root / "jobs")
    skills = load_skill_catalog(seed_root / "skills" / "skills.json")
    industries = load_industry_catalog(seed_root / "industries" / "naics-2022.json")
    assert len(jobs) == 16
    assert len({job.job_id for job in jobs}) == 16
    sourced_jobs = [job for job in jobs if job.source_url is not None]
    assert len(sourced_jobs) == 10
    assert all(job.source_url.startswith("https://") for job in sourced_jobs)
    assert all(job.source_checked_at is not None for job in sourced_jobs)
    assert all(len(job.summary.split()) >= 35 for job in jobs)
    skill_ids = {skill.skill_id for skill in skills.skills}
    assert len(skill_ids) == len(skills.skills)
    assert all(job.country_code == "GB" for job in jobs)
    assert all(job.minimum_education_level for job in jobs[:6])
    poc_locations = [job.location_label for job in jobs[:6]]
    assert all(poc_locations)
    assert len(set(poc_locations)) == 6
    assert all(set(job.required_skill_ids) <= skill_ids for job in jobs)
    assert all(set(job.preferred_skill_ids) <= skill_ids for job in jobs)
    assert {job.requirements_version for job in jobs} == {"job-requirements-v1"}
    assert {job.skill_catalog_version for job in jobs} == {skills.version}
    assert {job.industry_catalog_version for job in jobs} == {industries.version}
    assert {
        job.title: job.minimum_experience_months
        for job in jobs
        if job.minimum_experience_months is not None
    } == {
        "Registered Nurse": 6,
        "Cabin Crew – Talent Pool": 12,
        "Senior Product Manager": 24,
    }
    assert sum(skill.source == SkillSource.ONET for skill in skills.skills) == 15
    assert len(industries.industries) == 20
    assert len({industry.naics_code for industry in industries.industries}) == 20
    industry_ids = {industry.industry_id for industry in industries.industries}
    assert all(job.industry_id in industry_ids for job in jobs)
    industry_labels = {
        industry.industry_id: industry.preferred_label for industry in industries.industries
    }
    sourced_industries = {industry_labels[job.industry_id] for job in sourced_jobs}
    assert {
        "Health Care and Social Assistance",
        "Retail Trade",
        "Accommodation and Food Services",
        "Transportation and Warehousing",
        "Administrative and Support and Waste Management and Remediation Services",
    } <= sourced_industries
