# Job Matcher Decision Log

This document records what was chosen, who chose it, why it was chosen, and what it means
for the current proof of concept. It separates reasons stated by the product owner from
engineering rationale added during implementation. Where the reason is not yet known, it
is marked **Rationale to confirm** instead of being guessed.

## Product experience

### One-action welcome page

**Decision:** The first screen says “Welcome to Job Matcher” and has one primary action:
**Upload your resume**.

**Product-owner reason:** Keep the application and its purpose immediately understandable.

**Implementation:** The React interface accepts PDF or DOCX files and moves directly to a
three-stage processing screen.

### Automatic progression with no edit or confirmation step

**Decision:** After extraction, the profile is read-only and matching continues
automatically. The user does not edit fields or answer “Does this look correct?”.

**Product-owner reason:** Editing and confirmation were explicitly removed because they
made the POC too complex.

**Implementation consequence:** Incorrect extraction is visible but cannot be corrected in
the current UI. Evidence grounding, conservative mapping, and visible unmapped skills are
therefore especially important.

### Return exactly three jobs

**Decision:** Show the top three matches from a bundled standard dataset, with where the CV
matches, where it does not, and truthful actions that could close each documented gap.

**Product-owner reason:** Deliver one small, focused outcome rather than a general job-search
platform.

**Engineering implementation:** Six read-only job fixtures give enough candidates to rank a
top three without building job ingestion, administration, or external search.

### Simple processing feedback

**Decision:** Show progress as “Reading your CV → Building your profile → Finding your
matches”.

**Engineering reason:** These stages match the recoverable backend checkpoints and explain
real work without exposing internal model details.

## Data lifecycle

### Temporary POC data

**Decision:** Do not permanently save uploaded CVs, extracted profiles, working job copies,
or match results in the POC.

**Implementation:**

- The original PDF/DOCX is deleted immediately after successful text extraction.
- Extracted text, the grounded profile, and results remain in one UUID-scoped temporary
  session because later stages and crash recovery need them.
- Choosing another CV explicitly deletes the entire session.
- Leaving the experience stops its heartbeat. The server deletes the session after ten
  minutes without a heartbeat; a browser cannot reliably guarantee an immediate final
  close message.
- Refreshing the page restores the active session from browser session storage; it does
  not delete it.
- Embedding vectors exist only in worker memory. The persistent embedding Docker volume
  contains model weights, not CV content or candidate vectors.

**Product-owner reason:** Reduce the scope of the POC. Its intended development and
demonstration data is synthetic, so this decision is not being presented as a privacy or
regulatory compliance measure. Any later use with real CVs would require a separate privacy,
security, and retention review.

### Future authenticated product retention

**Decision:** A real product would tie data to an authenticated user profile and retain the
original CV as well as derived profile and match data under user controls.

**Product-owner reason:** Keeping the source CV allows it to be reprocessed when extraction,
standardization, or matching improves.

### UUIDs for identities

**Decision:** All public and stored identities use UUIDs. Root records use UUIDv4; retryable
derived records use deterministic UUIDv5 values.

**Engineering effect:** IDs are non-sequential, session paths are isolated, and retries can
recreate the same derived identity without duplication.

**Product-owner reason:** UUIDs are good practice for identities that may be public or
created independently by different parts of a system.

**Qualification:** UUIDs are appropriate here, but they are not universally better than
integer database keys and do not provide authorization by themselves. UUIDv4 suits
independently created root records; deterministic UUIDv5 suits retryable derived records.

## Reading and understanding documents

### Parse the document before using a model

**Decision:** A normal PDF/DOCX reader recovers text and source locations before AI is used.

**Engineering reason:** File parsers are more reliable and efficient for document structure,
and source blocks allow later facts to cite the actual CV.

**Current boundary:** Text-based PDF and DOCX are supported. OCR for scanned CVs is recorded
as a future update, as requested.

### Dedicated local vLLM service

**Decision:** Run the generation LLM in its own Docker container through vLLM.

**Current model:** `unsloth/Qwen3.6-35B-A3B-NVFP4-Fast`, exposed to the application as
`job-matcher-llm`.

**Engineering reason:** The service boundary makes model startup, GPU allocation, caching,
health checks, and provider replacement independent of the application code.

**Product-owner reason:** The model service can be scaled separately from the application,
and the boundary makes a later GPU-vendor change more manageable.

**Qualification:** Vendor portability applies at the service boundary, not to one unchanged
container. Each deployment still has a fixed, vendor-specific hardware/runtime
configuration. Moving from NVIDIA CUDA to AMD ROCm or Intel XPU can require a different
image, dependencies, kernel support, and model quantization. The current NVFP4 checkpoint
is specifically suited to the current NVIDIA Blackwell configuration.

### Grounded extraction, not model-authored facts

**Decision:** The LLM extracts experience, skills, qualifications, education, country, and
industry in separate schema-constrained passes. Degrees go in Education; certifications,
licences, and other formal non-degree awards go in Qualifications.

**Product-owner rule:** Degrees belong in Education; every other formal credential belongs
in Qualifications.

**Engineering interpretation:** This keeps degree-level matching separate from evidence of
certifications and licences.

**Engineering safeguards:** Proposed facts are checked against the source text, exact
evidence is reconstructed, current/latest work is surfaced first, and unsupported claims
are discarded.

## Standard categories

### Four comparison categories

**Decision:** Keep comparison to Education level, Skills, Location at country level, and
Industry.

**Product-owner reason:** Keep matching simple and standard enough for a one-to-one database
comparison.

**Implementation:** Education maps to EQF levels 4–8, location to ISO country codes, industry
to 2022 NAICS sectors, and skills to stable catalogue UUIDs.

### ESCO, O*NET, NAICS, and local extensions

**Decision:** Use European ESCO skill concepts, add U.S. O*NET transferable-skill concepts,
and add U.S. NAICS industry sectors. Modern technologies without a suitable official concept
use clearly labelled local extensions.

**Engineering reason:** One reviewed catalogue gives CV and job phrases stable identities
without falsely presenting local concepts as official standard entries.

**Product-owner reason:** Provide European and North American coverage while aligning skills
with an explicit industry classification. Worldwide taxonomy coverage is not part of the
current scope.

### LLM extraction followed by semantic mapping

**Decision:** Extract all explicit skills from both CVs and jobs with the LLM, then map those
phrases to the standard catalogue with vectors.

**Engineering interpretation:** Free-text CVs and job descriptions use different wording
even when they refer to the same skill, so exact string aliases alone are too conservative.

**Product-owner reasons:** Handle synonyms and paraphrases, and scale more economically. The
large generation model performs compact structured extraction once; the smaller embedding
model handles repeated phrase-to-catalogue comparisons. This avoids repeatedly asking the
large model to compare every skill concept or judge every match.

**Cost qualification:** The saving comes from compact LLM inputs and outputs plus delegating
repeatable semantic work to the smaller model. A deliberately large generated LLM output
would normally be slower and more expensive, not cheaper.

**Implementation:** Exact aliases are accepted first. Unresolved phrases are compared with
catalogue descriptions using Snowflake Arctic Embed 2.0. Weak or ambiguous results remain
unmapped and cannot score.

### Snowflake Arctic Embed 2.0

**Decision:** Use the Arctic 2.0 semantic embedding family.

**Engineering selection:** The POC currently uses
`Snowflake/snowflake-arctic-embed-m-v2.0`, the 768-dimensional medium variant, in a separate
CPU-only Text Embeddings Inference container. The medium model was selected to keep the GPU
available for vLLM and reduce POC resource use.

**Model-specific implementation:** Candidate phrases use the required `query: ` prefix;
catalogue descriptions do not. A small synthetic calibration selected a cosine minimum of
`0.25` and a runner-up margin of `0.04`. These are reviewable POC cutoffs, not probabilities.

**Product-owner reason:** Arctic 2.0 was selected as a high-performance semantic embedding
family.

**Qualification:** High performance is supported by the published retrieval benchmarks but
must still be measured on a labelled Job Matcher dataset. The medium variant was an
engineering choice for efficient local CPU inference; the product decision specified the
Arctic 2.0 family rather than a particular size.

## Matching and scoring

### Exact database match after standardization

**Decision:** Matching itself is a one-to-one database comparison of standardized facts.

**Implementation:** A temporary in-memory SQLite database joins identical skill UUIDs,
education keys, ISO country codes, and NAICS industry UUIDs. A higher education level also
satisfies each lower minimum. Every result is either **Met** or **Missing**; there is no
partial state.

**Engineering reason:** The same inputs produce the same result, and neither the LLM nor the
embedding model can inflate a fit decision after standardization.

### Current weighting

**Decision implemented:** Required matches determine ranking before preferred matches.
Within those groups, each documented requirement currently contributes one count. Stable
title and UUID ordering resolve final ties.

**Future scoring intent:** The product owner ultimately wants all three layers: required
versus preferred weighting, different category weights, and one overall normalized
percentage. The formula, actual weights, interpretation, and evaluation are deliberately
pinned for a separate scoring review. They are not part of the current implementation or
presented as settled policy. The UI currently shows numeric Met/Missing category counts.

## Reliability and safety

### Recoverable background processing

**Decision:** Upload processing is asynchronous and crash-recoverable while the temporary
session remains active.

**Implementation:** Each completed stage is atomically saved. A lease prevents simultaneous
workers, expired leases are reclaimed after restart, and transient failures retry up to three
times. A restarted matching stage may re-extract bundled job skills because that cache is
intentionally process-memory only.

**Engineering reason:** A model or container restart should not force the user to upload the
CV again or repeat already completed document work.

### Safe failure behaviour

**Decision:** Unsupported or ambiguous information is omitted instead of guessed. Failed
sessions show a safe retry route without including CV content in logs or error text.

**Engineering reason:** Missing data lowers a match transparently; invented data would make
the score misleading.

## Current verification and runtime state

As of 22 August 2026:

- 38 backend tests pass, with one dependency deprecation warning.
- Backend lint and the frontend production build pass.
- Arctic Embed 2.0 Medium returned ordered 768-dimensional vectors through the live CPU
  service.
- Synthetic calibration accepted clear paraphrases and rejected ambiguous or unrelated
  examples using the current cutoffs.
- A full post-Arctic synthetic upload was started but intentionally interrupted before
  completion when the GPU was needed for other work; it is not recorded as an end-to-end
  pass.
- The Job Matcher vLLM container and ComfyUI were stopped to release GPU memory.
- The frontend, API, and CPU-only Arctic service remain running. Uploads cannot complete
  model extraction until vLLM is started again.

## Deliberately deferred

- OCR for scanned CVs.
- CV editing and manual correction.
- User accounts and production retention controls.
- User-supplied job descriptions and job administration.
- Detailed location, remote-work, visa, and relocation rules.
- Large-catalogue retrieval and cross-encoder reranking.
- The separately pinned scoring review: importance weights, category weights, and the
  normalized overall percentage.
- A labelled evaluation set large enough to tune mapping or scoring policy.
