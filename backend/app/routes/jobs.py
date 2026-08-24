from fastapi import APIRouter, Request

from app.domain import AvailableJob

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=list[AvailableJob])
def list_available_jobs(request: Request) -> list[AvailableJob]:
    industries = {
        industry.industry_id: industry.preferred_label
        for industry in request.app.state.industry_catalog.industries
    }
    return [
        AvailableJob(
            job_id=job.job_id,
            title=job.title,
            company=job.company,
            summary=job.summary,
            responsibilities=job.responsibilities,
            required_qualifications=job.required_qualifications,
            preferred_qualifications=job.preferred_qualifications,
            minimum_education_level=job.minimum_education_level,
            country_code=job.country_code,
            industry_label=industries[job.industry_id],
            location_label=job.location_label,
            work_pattern=job.work_pattern,
            employment_type=job.employment_type,
            salary=job.salary,
            source_url=job.source_url,
            source_checked_at=job.source_checked_at,
        )
        for job in request.app.state.jobs
    ]
