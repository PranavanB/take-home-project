import json
from pathlib import Path

from app.domain import IndustryCatalog, JobFixture, SkillCatalog, SkillSource


class CatalogError(ValueError):
    pass


def load_job_dataset(root: Path) -> list[JobFixture]:
    files = sorted(root.glob("*.json"))
    if len(files) != 16:
        raise CatalogError(f"Expected exactly 16 job fixtures in {root}, found {len(files)}")

    jobs = [
        JobFixture.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in files
    ]
    ids = {job.job_id for job in jobs}
    if len(ids) != len(jobs):
        raise CatalogError("Job fixture UUIDs must be unique")
    versions = {job.requirements_version for job in jobs}
    if len(versions) != 1:
        raise CatalogError("Job fixtures must use one requirements version")
    return jobs


def load_skill_catalog(path: Path) -> SkillCatalog:
    if not path.is_file():
        raise CatalogError(f"Skill catalog not found: {path}")
    catalog = SkillCatalog.model_validate(json.loads(path.read_text(encoding="utf-8")))
    ids = {skill.skill_id for skill in catalog.skills}
    if len(ids) != len(catalog.skills):
        raise CatalogError("Standard skill UUIDs must be unique")

    aliases: dict[str, str] = {}
    for skill in catalog.skills:
        if skill.source == SkillSource.ESCO and not skill.concept_uri.endswith(
            str(skill.skill_id)
        ):
            raise CatalogError("ESCO concept URI must end with its skill UUID")
        if skill.source == SkillSource.ONET:
            if not skill.concept_uri.startswith(
                "https://www.onetcenter.org/ctdlasn/resources/"
            ):
                raise CatalogError("O*NET concept URI must use the official resource host")
            if skill.standard_code is None:
                raise CatalogError("O*NET skills must include their Content Model code")
        for alias in skill.aliases:
            key = alias.casefold()
            existing = aliases.get(key)
            if existing is not None and existing != str(skill.skill_id):
                raise CatalogError(f"Skill alias is ambiguous: {alias}")
            aliases[key] = str(skill.skill_id)
    return catalog


def load_industry_catalog(path: Path) -> IndustryCatalog:
    if not path.is_file():
        raise CatalogError(f"Industry catalog not found: {path}")
    catalog = IndustryCatalog.model_validate(json.loads(path.read_text(encoding="utf-8")))
    ids = {industry.industry_id for industry in catalog.industries}
    codes = {industry.naics_code for industry in catalog.industries}
    if len(ids) != len(catalog.industries):
        raise CatalogError("NAICS industry UUIDs must be unique")
    if len(codes) != len(catalog.industries):
        raise CatalogError("NAICS industry codes must be unique")

    aliases: dict[str, str] = {}
    for industry in catalog.industries:
        if (
            "https://www.census.gov/naics/" not in industry.concept_uri
            or f"details={industry.naics_code}" not in industry.concept_uri
            or "year=2022" not in industry.concept_uri
        ):
            raise CatalogError("NAICS concept URI must use the official 2022 sector page")
        for alias in industry.aliases:
            key = alias.casefold()
            existing = aliases.get(key)
            if existing is not None and existing != industry.naics_code:
                raise CatalogError(f"Industry alias is ambiguous: {alias}")
            aliases[key] = industry.naics_code
    return catalog
