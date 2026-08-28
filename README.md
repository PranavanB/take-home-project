# Job Matcher

Job Matcher is a focused CV matching proof of concept. A user uploads one CV,
sees a read-only standardized profile, and receives three matches from a bundled 16-job
dataset: six synthetic POC roles and ten roles researched from current employer listings.
The researched set is deliberately mixed: five technology roles and five roles from
healthcare, retail, hospitality, facilities services, and aviation.
After selecting a match, the user can ask a temporary career assistant about alignment,
gaps, or interview preparation using the standardized candidate and job facts.

## How matching works

The local vLLM service extracts grounded CV facts, including skills stated inside employment
history rather than only a dedicated skills section. Snowflake Arctic Embed 2.0 maps
unfamiliar skill wording to the reviewed skill catalogue. The 16 bundled jobs already hold
persisted, versioned normalized requirements, so they are not reinterpreted for each CV.
Application code reduces both sides to the same five categories:

- education level, aligned to EQF levels 4–8;
- skills, stored as UUIDs from a versioned ESCO- and O*NET-backed catalogue;
- total dated experience, stored as an exact minimum-month key;
- location, stored as an ISO country code; and
- industry, stored as a 2022 NAICS sector UUID.

The match itself is an exact join in a temporary in-memory SQLite database. It does not
ask the language model to judge fit. Results are either **Met** or **Missing**. Ranking uses
explicit POC category weights—Skills 40%, Experience 25%, Education 15%, Location 10%, and
Industry 10%—with required coverage considered before preferred coverage. Job titles are
display fields and never affect the match or its tie-breaks.

## Current features

- **Safe CV intake:** accepts validated PDF and DOCX files, preserves source locations for
  evidence, and deletes the raw upload as soon as text extraction succeeds.
- **Grounded profile extraction:** a schema-constrained local vLLM extracts the candidate's
  experience, skills, education, qualifications, country, and industry without inventing
  unsupported facts.
- **Standardized candidate data:** education maps to EQF levels, locations to ISO country
  codes, industries to NAICS sectors, and dated roles to non-overlapping experience months.
- **Reviewed skill mapping:** exact aliases and Arctic Embed 2.0 map CV wording to a
  versioned 56-concept ESCO/O*NET-backed catalogue; weak or ambiguous phrases remain
  visibly unmapped and cannot affect scoring.
- **Auditable job catalogue:** all 16 jobs have persisted, versioned requirements. The
  searchable mixed-sector jobs page includes dated source links for the ten
  employer-researched roles.
- **Deterministic matching:** an in-memory SQLite join compares five standardized categories
  and ranks the top three using explicit category weights. The LLM does not judge fit, and
  job titles do not influence the result.
- **Explainable results:** every match shows category percentages, Met/Missing requirements,
  supporting CV evidence, documented gaps, and truthful actions that could improve alignment.
- **Selected-match career chat:** the local LLM answers follow-up questions from a guarded
  system prompt containing the standardized profile and one selected match. Chat cannot
  change the deterministic score and is never written to the server-side session.
- **Recoverable temporary sessions:** UUID-backed processing checkpoints survive service
  restarts, retry transient failures, and delete the complete session after reset or expiry.
- **Tested responsive interface:** a React frontend supports the complete focused journey,
  backed by 43 deterministic backend tests, lint checks, and a production build check.

This product includes information from the O*NET 30.3 Database by the U.S. Department
of Labor, Employment and Training Administration (USDOL/ETA), used under the
[CC BY 4.0 license](https://creativecommons.org/licenses/by/4.0/). O*NET® is a trademark
of USDOL/ETA. Job Matcher has added its own aliases and UUIDs; USDOL/ETA has not approved,
endorsed, or tested those changes.

## Documentation

- [How Job Matcher works](docs/how-it-works.md) explains every process in plain English.
- [Implementation plan](plan.md) contains the broader build decisions and scope.

## Run with Docker

Copy `.env.models.example` to `.env.models`, then start the complete stack:

```powershell
docker compose --env-file .env.models --profile models up -d --build
```

The web interface is available at `http://127.0.0.1:5173/`. Model files and compiled
kernels use Docker volumes, so normal container rebuilds do not download them again.

If `make` is installed, the equivalent project shortcuts are:

```powershell
make up-models      # build/start the API, frontend, vLLM, and Arctic
make down-models    # stop vLLM and Arctic while leaving the web app available
```

## Local development

Backend:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".\backend[dev]"
$env:PYTHONPATH = ".\backend"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8015
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

Or run only the API and frontend with `docker compose up --build` when compatible LLM
and embedding endpoints are already available. The jobs catalogue remains usable when the
local model services are stopped, but a new CV cannot finish processing without both model
endpoints.

To release the GPU while leaving the API and frontend available for interface and catalogue
work:

```powershell
make down-models
```

The equivalent direct Docker command is
`docker compose --env-file .env.models --profile models stop vllm embedding`.
