# Job Matcher — Project Plan

## Overall goal

Job Matcher helps a user understand which available jobs best match their CV.

The user uploads one PDF or DOCX CV. The application extracts a structured profile,
standardizes the relevant information, compares it with the available jobs, and returns
the three strongest matches. Each result explains what matched, what is missing, and what
the user could do to close the documented gaps. The user can then ask questions about one
selected match using the same standardized candidate and job facts.

The application should remain simple, understandable, and trustworthy. AI is used to
interpret document language, while deterministic application code makes the final matching
and ranking decisions.

## Decisions made to achieve the goal

### 1. Keep the user journey focused

**Decision:** The main journey is:

1. Upload a CV.
2. See that it is being processed.
3. View the extracted profile.
4. Receive the top three job matches.

The landing page also links to a read-only page showing all available jobs.

**Why:** A short journey makes the product easy to understand and keeps attention on its
main purpose: turning a CV into useful, explainable job matches.

**Compromise:** Users cannot edit the extracted profile, upload their own jobs, or manage a
personal dashboard. If extraction is wrong, they must upload a revised CV or try again.

### 2. Use a bundled job catalogue

**Decision:** The application matches candidates against 16 bundled jobs covering several
industries and locations. These jobs are prepared and standardized before matching.

**Why:** A fixed catalogue makes the matching behaviour repeatable and allows the complete
experience to work without job-feed integrations or an administration system.

**Compromise:** The catalogue is small and does not update automatically. A larger product
would need a job-ingestion process that extracts, validates, versions, and standardizes new
vacancies before publishing them to the matcher.

### 3. Read the document before using AI

**Decision:** Standard PDF and DOCX parsers first recover the CV text and its source
locations. The language model then extracts structured facts from that recovered text.

**Why:** File parsers are more reliable than a language model for basic document reading.
Keeping page or paragraph references also lets extracted facts remain connected to evidence
from the original CV.

**Compromise:** Text-based PDF and DOCX files are supported, but scanned documents requiring
OCR are not. Complex visual layouts may also lose some formatting during extraction.

### 4. Use AI for extraction, not for the final judgement

**Decision:** A locally served language model extracts explicit experience, skills,
education, qualifications, location, and industry. It must attach evidence from the CV, and
unsupported facts are rejected. Job titles are displayed but do not affect matching because
titles are inconsistent and can be invented by employers.

**Why:** CVs and job descriptions express the same ideas in many different ways. A language
model is useful for turning that varied language into structured facts, but an AI-generated
fit judgement would be difficult to reproduce or audit.

**Compromise:** Conservative validation can omit a genuine fact when the evidence is unclear.
This is preferred to adding an unsupported skill or qualification that could inflate a
match.

### 5. Standardize both CVs and jobs into five categories

**Decision:** Candidate and job information is reduced to the same five comparison
categories:

- Education level
- Skills
- Total dated experience
- Location at country level
- Industry

Education uses EQF levels, countries use ISO codes, industries use NAICS identifiers, and
skills use stable UUIDs from a reviewed catalogue based on ESCO, O*NET, and clearly labelled
local additions. Degrees belong in Education; certifications, licences, and other formal
credentials belong in Qualifications.

**Why:** Standard categories allow CV facts and job requirements to be compared directly,
even when their original wording is different.

**Compromise:** Country-level location and broad industry categories lose detail. The current
skill catalogue is designed for the bundled jobs rather than the entire labour market. The
application extracts qualifications but does not yet score role-specific licences or
certifications.

### 6. Map skill wording with semantic embeddings

**Decision:** Exact aliases are checked first. Unresolved skill phrases are mapped to the
standard catalogue using Snowflake Arctic Embed 2.0. Weak or ambiguous mappings remain
unmapped and cannot contribute to a score.

**Why:** Exact text matching misses common synonyms and paraphrases. Embeddings help connect
phrases with the same meaning while stable catalogue IDs keep the later comparison simple.
Using a smaller embedding model for repeated mapping also avoids asking the larger language
model to judge every comparison.

**Compromise:** Semantic similarity can create false matches. Minimum similarity and
ambiguity thresholds reduce this risk, but the thresholds still need evaluation against a
larger labelled set of real CV and job phrases.

### 7. Keep model services separate from the application

**Decision:** The generation model runs through vLLM in its own Docker service. Arctic runs
in a separate CPU embedding service. The application communicates with both through stable
HTTP interfaces.

**Why:** The services can be started, stopped, monitored, and scaled independently. The
boundary also makes it easier to replace a model or move to another GPU vendor without
rewriting the application.

**Compromise:** The boundary is portable, but the model container itself is not universally
portable. Different GPU vendors can require different images, drivers, runtimes, and model
formats. Running several services also makes local startup heavier than using one hosted
model API.

### 8. Make matching deterministic and explainable

**Decision:** After standardization, an in-memory SQLite database compares candidate facts
with job requirements. Each requirement is either **Met** or **Missing**. The ranking uses
the following category weights:

- Skills: 40%
- Experience: 25%
- Education: 15%
- Location: 10%
- Industry: 10%

Required coverage determines the main order, and preferred coverage breaks ties. The three
highest-ranked jobs are returned with evidence, category scores, gaps, and practical actions.

**Why:** Deterministic matching produces the same result from the same facts. It is easier to
test and explain than asking a language model to assign a fit score directly.

**Compromise:** The initial weights are product choices rather than validated labour-market
rules. A separate scoring review is needed before presenting an overall percentage as a
universal measure of candidate suitability.

### 9. Use UUIDs for identities

**Decision:** Sessions, jobs, profiles, requirements, evidence, and results use UUIDs. New
root records use UUIDv4, while repeatable derived records use deterministic UUIDv5 values.

**Why:** UUIDs allow different parts of the system to create non-sequential identities
independently. Deterministic UUIDs also let a retry recreate the same derived record without
producing duplicates.

**Compromise:** UUIDs are less readable during debugging and use more space than small
integer keys. They are identifiers, not an authorization mechanism.

### 10. Keep user data temporary but processing recoverable

**Decision:** Each upload receives a temporary UUID-scoped session. The original file is
deleted after successful text extraction. Derived text, profile data, and results remain only
long enough to finish and display the match. Starting again deletes the session immediately;
inactive sessions expire after ten minutes.

Processing runs in recoverable stages. Completed stages are saved atomically, and an
interrupted worker can resume from the last completed stage while the session is still
active.

**Why:** Temporary storage keeps the current application small, while stage recovery avoids
forcing the user to upload the CV again after a model or container restart.

**Compromise:** Users cannot return later to view earlier matches. A full product would use
authenticated profiles, explicit retention controls, and secure long-term storage. It would
retain the original CV so improved extraction and matching systems could reprocess it.

### 11. Add questions without allowing AI to change the match

**Decision:** Each result includes a small career-assistant chat. The backend builds the
system prompt from the standardized candidate profile and one selected job match. It sends
only the recent conversation with each question. The model explains the recorded match,
skill gaps, experience alignment, and interview preparation, but it cannot write to the
profile or alter the deterministic score.

**Why:** Structured results answer the expected questions, while a conversation lets users
explore the parts that matter to them without requiring a new workflow. Supplying the
already-standardized facts also keeps the prompt smaller and avoids asking the model to read
or reinterpret the original CV for every question.

**Compromise:** Answers are generated and can still be incomplete, so the system prompt
requires the model to identify missing information and avoid inventing evidence. Chat works
only for the selected top-three result, remains in browser memory, and disappears with the
temporary session.

## Deferred work

The following improvements are valuable but are not part of the current build:

- OCR for scanned CVs
- Profile editing and correction
- User accounts and saved match history
- Automated job ingestion and administration
- City, distance, remote-work, visa, and relocation rules
- Role-specific licence and certification matching
- A broader skills catalogue
- Large-catalogue retrieval and reranking
- Validation of the category weights and overall score
- A labelled evaluation set for skill mapping and match quality
- Production monitoring, rate limiting, and multi-user isolation

Detailed process explanations are recorded in `docs/how-it-works.md`.
