# Build Progress and Rationale

This records what is implemented in the Job Matcher POC as of 23 August 2026 and why the
main choices were made.

## Complete user journey

The application now supports the full focused path:

1. upload one PDF or DOCX CV;
2. read it into source-aware text;
3. extract and validate a temporary candidate profile with vLLM;
4. extract job skills and use exact aliases plus Arctic Embed 2.0 to standardize CV and
   job skill wording;
5. standardize education, country, and industry;
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

### Job skill extraction

- The same schema-constrained local LLM extracts every explicitly supported required and
  preferred skill from titles, summaries, responsibilities, and qualification lists.
- The same Arctic mapper standardizes both jobs and CVs.
- A required occurrence takes precedence over a duplicate preferred occurrence.
- Normalized jobs are cached in process memory and rebuilt safely after an API restart.

Why: mapping both sides through one route prevents a carefully normalized CV from being
compared with unprocessed job wording. The LLM identifies phrases; it does not grade fit.

### Four standard comparison categories

- Education mapped to Secondary, Vocational, Bachelor's, Master's, or Doctorate and EQF
  levels 4–8.
- Skills stored as standardized UUIDs.
- Location stored as an ISO two-letter country code.
- Industry stored as one of 20 top-level 2022 NAICS sectors with a stable UUID.
- Every raw job fixture stores a country code, one NAICS industry UUID, and reviewed
  required and preferred skill UUIDs. Education is present only when a requirement is
  stated; the matcher does not invent one. Live job skill normalization can produce a
  different reviewed set from explicit job text.

Why: four shared fields keep the match comprehensible and eliminate free-text grading.

### Deterministic matching

- A new in-memory SQLite database for each match calculation.
- Exact joins on skill UUID, education key, country code, or NAICS industry UUID.
- Higher education contributes every lower minimum it satisfies.
- Only **Met** and **Missing** statuses; Partial has been removed.
- Required coverage ranks first, preferred coverage breaks ties, and stable fields resolve
  final ties.
- Exactly three results are retained in the temporary session.
- The language model and vector service finish standardization before the database matcher
  starts; neither is allowed to change a Met/Missing decision inside the join.

Why: identical data produces identical outcomes. The model cannot make subjective fit
judgments, and free-text skills cannot accidentally score.

### Results interface

- Current/latest role remains the profile headline.
- The visible comparison profile contains Education level, Standardized skills, Location,
  and Industry only.
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
  Location, and Industry counts for the selected role.
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
- O*NET skill alias standardization;
- deterministic top-three ordering;
- education and country extraction;
- exact skill alias standardization;
- Arctic query/document prompt handling, response ordering, and vector validation;
- semantic vector mapping with similarity and ambiguity rejection;
- LLM job-skill extraction, deduplication, and normalization; and
- the complete upload-to-three-results API journey.

Current local verification:

- 39 backend tests pass;
- backend lint passes;
- the frontend production build passes;
- browser checks confirm all 16 cards render, sector searches return the expected roles,
  employer-job details expand correctly, and the jobs page works at a mobile viewport;
- an earlier synthetic live upload through the rebuilt vLLM pipeline extracted
  Bachelor's/EQF 6,
  country GB, NAICS sector 54, and six standardized skills including O*NET Systems
  Analysis; every returned job contained all four category summaries and 11 exact
  requirement comparisons. A browser check also confirmed the O*NET badge and Industry
  category are visible in the results interface;
- the live CPU Arctic service returned ordered 768-dimensional embeddings and completed a
  12-phrase mapping calibration against all 56 catalogue entries; and
- the full post-Arctic synthetic upload was intentionally interrupted before completion
  when the GPU was released for other work, so that specific end-to-end route remains to
  be rerun.

Current runtime state: the frontend and API are running for catalogue and interface work.
The CPU-only Arctic service and vLLM container are stopped, so new uploads cannot complete
profile or job extraction until those services are restarted. The jobs catalogue does not
need either model service. This is an operational state, not an application failure.

Known command follow-up: the README's full `docker compose` command starts all four
services. The existing `make up-models` shortcut currently omits the `embedding` service
from its explicit target list and should be aligned before it is presented as the primary
startup command.

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
- Job retrieval and cross-encoder reranking for a future large job catalogue.
- The separately pinned scoring formula covering required/preferred weights, category
  weights, and one normalized overall percentage.

## Next review

Review the usefulness of the exact results with real examples. In particular, decide
whether the Arctic similarity cutoff and runner-up margin reject the right ambiguous
phrases and whether the resulting exact UUID matches are useful. Fit weighting has been
pinned for a separate review covering requirement importance, category importance, and an
overall normalized percentage. Any change should be measured against labelled examples
before it changes the matching policy.
