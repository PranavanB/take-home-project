# Job Matcher

Job Matcher is a focused CV matching proof of concept. A user uploads one CV,
sees a read-only standardized profile, and receives three matches from a bundled 16-job
dataset: six synthetic POC roles and ten roles researched from current employer listings.
The researched set is deliberately mixed: five technology roles and five roles from
healthcare, retail, hospitality, facilities services, and aviation.

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

- UUID-backed temporary sessions with crash recovery and bounded retries
- PDF/DOCX validation and source-aware text extraction
- Raw CV deletion immediately after successful reading
- Grounded, schema-constrained profile extraction through a separate vLLM container
- Skill extraction from all parts of the CV, followed by Arctic Embed 2.0 vector mapping
- Conservative vector acceptance: ambiguous or weak mappings remain visibly unmapped
- Deterministic exact mapping for explicitly labelled CV industries
- 56 stable standardized skill concepts, 20 NAICS sectors, and 16 persisted, versioned
  normalized jobs
- Searchable available-jobs catalogue backed by the same 16-job matching dataset
- Source links and research dates for the ten employer-sourced listings
- A mixed-sector catalogue rather than a technology-only vacancy list
- Multi-sentence job descriptions and human-readable city or regional locations
- Exact education, skill, experience-duration, country, and industry matching
- Deterministic weighted top three with per-category percentages, evidence, and gap actions
- Heartbeat expiry and explicit whole-session deletion
- Test-first backend coverage and a responsive React interface

This product includes information from the O*NET 30.3 Database by the U.S. Department
of Labor, Employment and Training Administration (USDOL/ETA), used under the
[CC BY 4.0 license](https://creativecommons.org/licenses/by/4.0/). O*NET® is a trademark
of USDOL/ETA. Job Matcher has added its own aliases and UUIDs; USDOL/ETA has not approved,
endorsed, or tested those changes.

## Documentation

- [How Job Matcher works](docs/how-it-works.md) explains every process in plain English.
- [Build progress and rationale](docs/build-progress.md) records what is implemented,
  why, verification, and deferred work.
- [Decision log](docs/decision-log.md) separates confirmed product reasons, engineering
  rationale, and decisions whose motivation still needs confirmation.
- [Model smoke-test record](docs/model-smoke.md) records local model and hardware checks.
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
