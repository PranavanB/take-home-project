# How Job Matcher Works

This guide explains the proof of concept in plain English: what each process does and
why it was chosen.

## The short version

1. The user can search and review the 16 available jobs or upload a PDF or DOCX CV.
2. Job Matcher reads the document and uses the local language model to extract facts.
3. The local model also extracts every explicitly requested skill from each built-in job.
4. Exact aliases and Snowflake Arctic Embed 2.0 map skill phrases from both sides to the
   same reviewed catalogue.
5. Those facts are reduced to four matching categories: education level, standardized
   skills, country, and industry.
6. A temporary database compares identical keys and returns the top three jobs.
7. The results show exact matches, missing items, and truthful next actions.
8. The temporary session is deleted when the user resets it or its heartbeat expires.

The models extract and standardize evidence. They do not decide whether a job fits.

## 1. Landing page, available jobs, and temporary session

The welcome page has two actions: **Upload your resume** and **View available jobs**.
The jobs action opens a conventional, searchable catalogue containing all 16 roles used
by the matcher: six synthetic POC roles and ten roles researched from live employer job
pages. Each listing shows the job title, employer, location, description, work pattern,
salary where it was published, industry, responsibilities, and required and preferred
experience. A back action returns to the upload page, and the `/jobs` address can be
opened or refreshed directly.

Descriptions are substantial, plain-English overviews rather than one-line taglines. The
six synthetic POC roles use varied display locations in Manchester, Bristol, Cambridge,
Edinburgh, Birmingham, and Leeds. Employer-sourced locations remain faithful to their
linked adverts. These detailed locations help users understand the listing, but the POC
matcher still compares location only at country level (`GB`).

The ten employer-sourced records contain a link to the original listing and the date it
was checked. Their descriptions and requirements are concise paraphrases rather than
copies of the adverts. Employer vacancies can close or change after that date, so Job
Matcher presents them as a dated POC dataset rather than promising live availability.

The sourced half of the catalogue is intentionally balanced between five technology roles
and five non-technology roles: registered nursing, retail operations, professional
cooking, facilities cleaning, and cabin crew. Why: education, skills, location, and
industry matching should be demonstrated across different kinds of work, not mistaken for
a technology-only matcher.

The catalogue comes from a public read-only API backed by the same bundled job files used
for matching. It deliberately omits internal standardized skill UUIDs. Why: candidates can
understand the current opportunity set before sharing a CV, and using one data source keeps
the visible listing aligned with the actual matcher.

The upload action accepts text-based PDF and DOCX files up to 10 MB. It checks the real
file type and rejects empty, damaged, encrypted, oversized, or unsupported documents.

Every upload receives random UUIDs for the session, CV, and processing job. Temporary
artifacts live under the session UUID, so the whole visit can be deleted as one unit.

Why: two clearly separated actions keep the product focused while letting someone inspect
the dataset before starting a match. File checks prevent wasted model work, and UUID-scoped
storage makes cleanup and crash recovery predictable. UUIDs are appropriate for public or
independently created identities, although they are not a substitute for authorization and
are not automatically better than integers in every system.

## 2. Read the CV

A normal document parser extracts text first. PDF pages and ordered DOCX paragraphs or
tables retain source IDs. Scanned-image PDFs are not supported yet; OCR is a future
update.

Why: document parsers are faster and more reliable at recovering text than asking a
language model to read file formats. Source IDs also let every later claim point back to
the CV.

The uploaded PDF or DOCX is deleted as soon as text extraction succeeds. The extracted
text remains only inside the active temporary session because later stages need it.

## 3. Extract grounded CV facts

The local model runs in its own vLLM Docker service. This allows inference to scale
separately from the application and makes a later hardware-vendor migration easier at the
service boundary. Such a migration would still require a vendor-specific image, runtime,
and compatible model format; the current NVFP4 deployment is tied to the current NVIDIA
configuration.

The service receives the extracted text and returns six small structured responses:

- experience;
- skills;
- qualifications;
- education;
- current country, when explicitly stated; and
- current industry, when explicitly stated.

Degrees go under Education. Certifications, licences, and other formal non-degree awards
go under Qualifications. The current or latest position is placed first.

The application checks every proposed item against the source document and replaces the
model's evidence wording with an exact excerpt. Unsupported items are dropped. Missing
facts stay missing.

Why: the model is useful for understanding varied CV language, but application code must
control the schema, evidence, dates, identities, and safety rules.

## 4. Reduce the CV to four standard categories

The matching profile contains only these categories:

### Education level

Degree wording is converted to one ordered level:

| Standard level | EQF level |
|---|---:|
| Secondary education | 4 |
| Vocational qualification | 5 |
| Bachelor's degree | 6 |
| Master's degree | 7 |
| Doctorate | 8 |

The levels follow the European Qualifications Framework. A higher level satisfies a
lower minimum: for example, a Master's degree meets a Bachelor's requirement.

### Skills

The local language model first extracts the skill phrases exactly supported by the CV.
Each phrase then follows two mapping steps:

1. An exact, case-insensitive alias lookup is tried first. Exact matches are accepted with
   no vector inference.
2. Otherwise, Snowflake Arctic Embed 2.0 compares the phrase with descriptions of the
   reviewed catalogue concepts. The phrase is encoded as a query and the catalogue items
   as documents, following the model's retrieval instructions.

A vector result is accepted only when its cosine similarity clears the configured cutoff
and it is sufficiently ahead of the runner-up concept. Weak or ambiguous phrases remain
unmapped and cannot affect the score. The UI keeps these phrases visible so the user can
see what was extracted without pretending they matched a standard. A displayed similarity
is a model comparison value, not a probability that the person has the skill.

Accepted facts use catalogue UUIDs, not free text. The same mapper is used for CV and job
phrases, so different wording can converge on one identity before matching begins. This
also scales more economically: the large LLM creates compact structured facts once, then
the smaller embedding model performs the repeated catalogue comparisons.

The catalogue uses official ESCO concepts where ESCO has a suitable entry and a reviewed
subset of official O*NET 30.3 transferable skills for the U.S. skills standard. Modern product
names that are not suitable ESCO concepts, such as Docker, React, or Terraform, are
clearly labelled Job Matcher extensions with their own stable UUIDs. They are not
misrepresented as official ESCO concepts.

The POC catalogue contains 56 concepts and is deliberately versioned. It can later be
replaced by larger ESCO and O*NET imports without changing the matching contract. The
current scope deliberately covers European and North American terminology rather than a
worldwide taxonomy. The selected embedding model is
`Snowflake/snowflake-arctic-embed-m-v2.0`, served in its own CPU container so the main
generation model retains the GPU.

### Location

Location is one ISO two-letter country code, such as `GB`. City, distance, remote-work
rules, visas, and relocation are outside the POC.

### Industry

Industry is mapped to one of the 20 top-level sectors in the 2022 North American Industry
Classification System (NAICS). The system uses the current or most recent employer's
explicitly stated industry. It does not guess an industry from a company name.

When a CV contains an `Industry:`, `Sector:`, or `Business domain:` label, application
code reads the complete labelled value and accepts it only when it exactly matches a
reviewed NAICS alias. This deterministic check runs even if the language model omits the
field. It was chosen because an explicit label is already structured data and should not
depend on variable model behaviour.

The stored fact contains both the NAICS sector code and a stable UUID. The broad sector
level keeps the POC understandable; detailed three- to six-digit industries can be added
later if the product needs them.

Why: the same stable values can be stored on both CVs and jobs. This removes fuzzy wording
from the actual match and makes every result reproducible.

References: [Snowflake Arctic Embed 2.0](https://huggingface.co/Snowflake/snowflake-arctic-embed-m-v2.0),
[ESCO](https://esco.ec.europa.eu/en/about-esco/what-esco),
[O*NET 30.3](https://www.onetcenter.org/database.html),
[2022 NAICS](https://www.census.gov/programs-surveys/economic-census/year/2022/guidance/understanding-naics.html),
and [the eight EQF levels](https://europass.europa.eu/en/description-eight-eqf-levels).

## 5. Standardize the 16 jobs

Every bundled job fixture contains:

- a minimum education level when the source states one;
- required standardized skill UUIDs;
- one ISO country code;
- one NAICS industry sector; and
- preferred standardized skill UUIDs where relevant.

Before matching, the local language model reads the job title, summary, responsibilities,
and qualification lists and extracts every explicitly supported required or preferred
skill. Those phrases pass through the same exact-alias and Arctic vector mapper as the CV.
Required wins if the same skill appears in both lists, and unmapped phrases do not enter
the score. The normalized jobs are cached only in process memory for the running POC.

The job files and skill catalogue are read-only application data; they are not copied into
a permanent user database.

Why: a fixed 16-job dataset is enough to demonstrate a meaningful top-three choice and a
recognizable jobs page without building job administration, accounts, automated vacancy
feeds, or a large search platform. Keeping source metadata makes the ten researched roles
auditable even when an employer later changes or removes a listing.

### Future full-build job ingestion

The full product will replace manually prepared fixtures with a dedicated vacancy-ingestion
process. It will accept a job advert or trusted employer feed, retain the original source,
and break the vacancy into structured component parts:

- original and standardized job title;
- employer and source identity;
- country, city or region, and remote or hybrid rules;
- required and preferred skills;
- minimum education and formal qualifications;
- industry;
- responsibilities and experience requirements;
- employment type, work pattern, salary, and closing date where stated; and
- source URL, source evidence, and the time the advert was checked.

The language model will extract only information supported by the source advert. Application
code will then convert country to ISO codes, education to the agreed EQF levels, industry to
NAICS UUIDs, and skill phrases to the reviewed ESCO/O*NET-backed skill UUIDs using exact
aliases and Arctic vector mapping. Both the original title and a standardized title will be
kept; the production title taxonomy still needs to be selected and reviewed.

Before publication, the pipeline will validate required fields, flag weak or ambiguous
mappings for review, detect duplicate or updated adverts, and save the normalized job with
its provenance. Why: the exact database matcher can scale only when every vacancy reaches it
as the same predictable structure. Retaining the original source also allows jobs to be
reprocessed when extraction rules or taxonomies improve.

## 6. Exact database matching

For each match, Job Matcher creates a SQLite database in memory. It inserts the job
requirements and the candidate facts, then joins rows on an identical standard key:

- `skill:<UUID>` for skills;
- `education:<level>` for education; and
- `country:<ISO code>` for location; and
- `industry:<UUID>` for the NAICS sector.

For ordered education, the candidate contributes every minimum level they satisfy. A
Master's candidate therefore contributes exact facts for Master's, Bachelor's,
vocational, and secondary levels. The database join itself remains a simple exact match.

Free-text skills never enter this join. If a CV or job phrase cannot be mapped to a
catalogue UUID, it cannot create a fuzzy or partial match.

Why: exact database joins are simple, fast, testable, and explainable. The same inputs
always produce the same results, and the language model cannot inflate a score.

## 7. Results and ranking

Every requirement is either:

- **Met** — an identical standardized database fact exists; or
- **Missing** — it does not.

There is no Partial state in this version. Each job shows numeric Met/Missing counts for
Education, Skills, Location, and Industry. It also shows required and preferred totals.

Jobs are ordered by:

1. number of required items met;
2. number of preferred items met; and
3. title and UUID as stable tie-breakers.

Required items therefore carry more weight than preferred items without inventing an
unreviewed percentage. Exactly three jobs are returned. A later, separately pinned scoring
review will define required/preferred weights, category weights, and an overall normalized
percentage together; none of those formulas is settled yet.

Missing items include an honest action such as adding truthful CV evidence if the person
really has that skill. Complete coverage means only that every standardized database
requirement matched; it never guarantees an interview, offer, or real-world suitability.

The results page first presents the top three jobs as compact comparison cards. The first
job is selected automatically, and choosing another card replaces the single detailed
panel below it. This keeps required and preferred counts easy to compare without rendering
three long reports at once. The selected panel then shows category coverage, CV evidence,
gaps, and suggested next steps. The layout stacks into one column on narrow screens.

Why: counts expose precisely what happened. They are more useful and defensible than an
opaque AI fit score.

## 8. Progress, recovery, and deletion

The page shows three stages:

`Reading your CV → Building your profile → Finding your matches`

Each finished stage is saved atomically. If the API restarts, the worker validates the
newest saved artifact and continues from the next incomplete stage. A temporary failure
is retried up to three times, and the failure page can resume from saved session work.

The browser sends a heartbeat while the experience is open. Explicitly choosing another
CV deletes the session immediately. Closing the page stops heartbeats; after ten minutes
without one, cleanup removes the entire session. This expiry path also covers browser
crashes and lost connections.

Why: browsers cannot reliably promise a final “I am leaving” message. A short lease gives
the POC dependable deletion without allowing a transient page event to destroy active
processing.

## 9. What a real product would retain

This POC has no accounts and deletes everything session-specific. A real system would tie
data to an authenticated user profile and retain the user's CV, extracted profile, and
match history under a clear retention policy with user controls.

The original CV would be retained as well as the derived profile. If extraction,
standardization, or matching improves later, the system can reprocess the true source
rather than relying on an older interpretation.

## Future updates

- OCR for scanned CVs.
- A labelled mapping evaluation before enlarging the ESCO and O*NET catalogues or changing
  the Arctic similarity and ambiguity cutoffs.
- More detailed location rules, including remote, distance, visa, and relocation needs.
- Authenticated profiles, retention controls, and deletion/export tools.
- Automated job ingestion from employer feeds or submitted adverts, including validation,
  deduplication, standardization, provenance, and update/expiry handling.
- A labelled quality evaluation before changing the exact-match policy.
- Complete the separately pinned scoring review covering required/preferred weighting,
  category weighting, and the overall normalized percentage.

### O*NET attribution

This product includes information from the O*NET 30.3 Database by the U.S. Department of
Labor, Employment and Training Administration (USDOL/ETA), used under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). O*NET® is a trademark of
USDOL/ETA. Job Matcher added aliases and UUID identities; USDOL/ETA has not approved,
endorsed, or tested those changes.
