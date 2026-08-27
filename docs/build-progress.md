# Build Progress and Rationale

This records what is implemented in the Job Matcher POC as of 26 August 2026 and why the
main choices were made.

## Complete user journey

The application now supports the full focused path:

1. upload one PDF or DOCX CV;
2. read it into source-aware text;
3. extract and validate a temporary candidate profile with vLLM;
4. extract CV skills from the whole document and map them with exact aliases plus Arctic
   Embed 2.0 to the same catalogue used by the persisted job requirements;
5. standardize education, total dated experience, country, and industry;
6. compare those fields with all 16 bundled jobs through exact database joins;
7. show exactly three ranked jobs with numeric matches, gaps, evidence, and actions; and
8. clean up the temporary session after an explicit reset or heartbeat expiry.

## What is built

### Temporary POC sessions

- UUIDv4 identifiers for the session, CV, and ingest job.
- Deterministic UUIDv5 identifiers for retryable derived facts.
- One verified directory per session.
- Atomic manifest and artifact writes.
- Heartbeats, a ten-minute expiry lease, explicit reset deletion, and bounded cleanup.
- Stage recovery after an API restart and up to three retries per failed stage.

Why: the intended POC demonstrations use synthetic data and do not need accounts or a
permanent data database. Temporary storage is a scope decision, not a claimed privacy or
regulatory control. A UUID-scoped directory also makes lifecycle, recovery, and deletion
easy to reason about.

### Safe document reading

- Real PDF/DOCX signature checks and a 10 MB upload limit.
- PDF encryption, corruption, readability, and 25-page checks.
- DOCX structure and decompression-size checks.
- Source-aware PDF pages and ordered DOCX paragraph/table blocks.
- Raw upload deletion immediately after successful text extraction.

Why: normal parsers should recover document text before AI is involved. Source blocks
also give every extracted fact a stable evidence location.

### Grounded profile extraction

- A dedicated vLLM Docker service with schema-constrained output.
- Six focused passes: experience, skills, qualifications, education, country, and industry.
- Strict dates, degree classification, current-role ordering, deduplication, and bounds.
- Skills are extracted from employment history and responsibilities as well as Skills lists.
- Non-overlapping employment months are calculated and stored with an as-of date.
- Exact evidence reconstruction from the original extracted text.
- Deterministic recovery of exact NAICS values after explicit Industry, Sector, or
  Business domain labels when the model omits them.
- Unsupported model claims are omitted instead of entering the profile.
- A read-only UI; there is no editing or confirmation step.

Why: the model interprets varied CV wording, while application code owns validation,
identity, evidence, and safety.

### Standard skill catalogue

- A versioned catalogue containing 56 stable skill UUIDs.
- Official ESCO concept UUIDs and concept links where a suitable concept exists.
- Fifteen official O*NET 30.3 transferable-skill concepts with Content Model codes.
- Clearly labelled Job Matcher extensions for uncovered modern product names.
- Exact, case-insensitive alias mapping is attempted before any model call.
- `Snowflake/snowflake-arctic-embed-m-v2.0` maps unresolved CV and job phrases to
  catalogue descriptions in a separate CPU inference container.
- Arctic query phrases use the required `query: ` instruction; catalogue documents have
  no query prefix.
- Minimum similarity and runner-up margin checks reject weak or ambiguous mappings.
- Raw unmapped CV phrases remain visible but cannot affect the score.
- Validation for duplicate UUIDs, ambiguous aliases, and invalid ESCO/O*NET links.

Why: skills from CVs and jobs need the same identity. A small reviewed catalogue is
appropriate for 16 jobs and can later grow without changing the match API. Exact aliases
also avoid needless vector variability for already-known labels.

### Persisted job normalization

- Each of the 16 job files persists its reviewed required and preferred skill UUIDs.
- Each job records `job-requirements-v1` plus the exact skill- and industry-catalogue versions.
- Job titles are excluded from extraction and ranking because employers can invent them.
- Three adverts with explicit numeric minima persist 6, 12, or 24 months of experience;
  no duration is invented for the others.
- The future ingestion route uses the same LLM and Arctic mapper once, validates the result,
  and publishes a versioned record. Candidate matching does not re-extract jobs at runtime.

Why: mapping both sides through one route prevents a carefully normalized CV from being
compared with unprocessed job wording. Persisting the job result makes restarts deterministic
and avoids repeated LLM work. The LLM identifies phrases; it does not grade fit.

### Five standard comparison categories

- Education mapped to Secondary, Vocational, Bachelor's, Master's, or Doctorate and EQF
  levels 4–8.
- Skills stored as standardized UUIDs.
- Experience stored as total non-overlapping dated months.
- Location stored as an ISO two-letter country code.
- Industry stored as one of 20 top-level 2022 NAICS sectors with a stable UUID.
- Every raw job fixture stores a country code, one NAICS industry UUID, and reviewed
  required and preferred skill UUIDs. Education is present only when a requirement is
  stated; the matcher does not invent one. Numeric experience is present only when the
  advert states a minimum.

Why: five shared fields keep the match comprehensible and eliminate free-text grading.

### Deterministic matching

- A new in-memory SQLite database for each match calculation.
- Exact joins on skill UUID, education key, experience-month key, country code, or NAICS
  industry UUID.
- Higher education contributes every lower minimum it satisfies.
- Only **Met** and **Missing** statuses; Partial has been removed.
- Required weighted category coverage ranks first, preferred weighted category coverage
  breaks ties, and the stable job UUID resolves final ties.
- Explicit POC category weights are Skills 40%, Experience 25%, Education 15%, Location 10%,
  and Industry 10%; each category is normalized before its weight is applied.
- Exactly three results are retained in the temporary session.
- The language model and vector service finish standardization before the database matcher
  starts; neither is allowed to change a Met/Missing decision inside the join.

Why: identical data produces identical outcomes. The model cannot make subjective fit
judgments, and free-text skills cannot accidentally score.

### Results interface

- Current/latest role remains the profile headline.
- The visible comparison profile contains Education level, Standardized skills, dated
  Experience, Location, and Industry.
- The landing page has a **View available jobs** action backed by a public read-only API.
- The available-jobs page is a conventional searchable job board listing all 16 bundled
  roles: six synthetic POC roles and ten roles researched from employer job pages.
- The researched set contains five technology roles and five roles spanning health care,
  retail, accommodation and food services, facilities services, and transportation.
- Cards show title, employer, location, description, work pattern, salary when available,
  and industry. Expandable details show responsibilities and required/preferred experience.
- Every role has a multi-sentence overview. The six synthetic POC roles have distinct
  locations across Manchester, Bristol, Cambridge, Edinburgh, Birmingham, and Leeds;
  employer-sourced locations are not altered. City names are display information while the
  current matching contract remains country-level.
- The ten researched records link to the original employer listing and show a checked date;
  advert text is paraphrased, and the source may later change or expire.
- The top three matches first appear as compact selectable comparison cards.
- One focused detail panel shows required and preferred totals plus Education, Skills,
  Experience, Location, and Industry percentages, weights, and counts for the selected role.
- Expandable rows show exact evidence for matches and truthful next actions for gaps.

Why: candidates can inspect the opportunity set before uploading, and the displayed jobs
come from the same source used by matching. The results UI mirrors the database contract
without forcing the user to scroll through three complete reports. Users do not need to
interpret an opaque fit percentage or a vague Partial status.

## Test-first changes for standardized matching

Tests were written before the new matcher and cover:

- catalogue integrity and job references;
- identical standardized skill UUID matching;
- refusal to match raw free-text skills;
- Master's satisfying a Bachelor's minimum;
- exact ISO country-code behaviour;
- exact NAICS sector behaviour;
- non-overlapping experience-month calculation and exact minimum matching;
- explicit category-normalized ranking weights and title-neutral tie-breaking;
- persisted job and catalogue version validation;
- O*NET skill alias standardization;
- deterministic top-three ordering;
- education and country extraction;
- exact skill alias standardization;
- Arctic query/document prompt handling, response ordering, and vector validation;
- semantic vector mapping with similarity and ambiguity rejection;
- LLM job-skill extraction, deduplication, normalization, and title exclusion; and
- the complete upload-to-three-results API journey.

Current local verification:

- 44 backend tests pass (rerun on 26 August 2026);
- backend lint passes;
- the frontend production build passes;
- browser checks confirm all 16 cards render, sector searches return the expected roles,
  employer-job details expand correctly, and the jobs page works at a mobile viewport;
- an earlier synthetic live upload through the rebuilt vLLM pipeline extracted
  Bachelor's/EQF 6,
  country GB, NAICS sector 54, and six standardized skills including O*NET Systems
  Analysis; every returned job contained the earlier four category summaries and 11 exact
  requirement comparisons. A browser check also confirmed the O*NET badge and Industry
  category are visible in the results interface;
- the live CPU Arctic service returned ordered 768-dimensional embeddings and completed a
  12-phrase mapping calibration against all 56 catalogue entries; and
- the current five-category, persisted-job post-Arctic journey remains to be recorded as a
  complete live pass. An earlier post-Arctic upload was interrupted. On 26 August, both
  model services reached healthy status and vLLM exposed `job-matcher-llm`, but the automated
  in-app browser did not expose its file-selection event, so the synthetic PDF was not
  submitted before the user requested another GPU shutdown.

Current runtime state: the frontend and API are running for catalogue and interface work.
The CPU-only Arctic service and vLLM container are stopped, so new uploads cannot complete
CV profile extraction and skill mapping until those services are restarted. Persisted job
requirements and the jobs catalogue do not need either model service. This is an operational
state, not an application failure. ComfyUI and its Python process remain running as requested;
after the Job Matcher model services stopped, total GPU use was approximately 3,113 MiB.

The model lifecycle shortcuts are aligned with the complete stack: `make up-models` builds
and starts the API, frontend, vLLM, and Arctic; `make down-models` stops both model services
while leaving the API and frontend available. `make pull-models` pulls both model images.

The test-client dependency emits one deprecation warning from its compatibility layer;
it does not affect application behaviour.

## Deliberately deferred

- OCR for scanned CVs.
- CV editing and manual correction.
- Accounts and production retention controls.
- A production vacancy-ingestion pipeline for employer feeds or submitted job descriptions.
  It will extract title, employer, location, skills, education, qualifications, industry,
  duties, work pattern, salary, and source metadata; standardize those components; validate
  and deduplicate the result; retain provenance; and publish the normalized job catalogue.
- City/distance, remote, visa, and relocation matching.
- Certification, professional-qualification, and licence matching. Those facts are extracted
  now, but production should compare them where roles are regulated or credential-specific.
- Broader cross-sector skill-catalogue coverage beyond the 56 concepts needed by this dataset.
- Linking experience duration to individual roles, standardized skills, and domains.
- Job retrieval and cross-encoder reranking for a future large job catalogue.
- The separately pinned scoring review covering required/preferred weights, validation of the
  initial category weights, and one normalized overall percentage.

## Next review

Review the usefulness of the exact results with real examples. In particular, decide
whether the Arctic similarity cutoff and runner-up margin reject the right ambiguous
phrases and whether the resulting exact UUID matches are useful. Fit weighting has been
pinned for a separate review covering requirement importance, validation of the initial
category importance, and an overall normalized percentage. Country-only location and broad
NAICS sectors remain accepted POC simplifications. Any change should be measured against
labelled examples before it changes the matching policy.
