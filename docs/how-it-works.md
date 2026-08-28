# How Job Matcher Works

This document follows one CV through Job Matcher from upload to results. It describes what
the application does at runtime without repeating project decisions, implementation status,
or model test results.

For the reasons behind the design and its accepted compromises, see [`plan.md`](../plan.md).

## Process overview

```text
Upload CV
   ↓
Read document
   ↓
Extract evidence-backed profile
   ↓
Standardize candidate facts
   ↓
Compare with standardized jobs
   ↓
Rank all jobs
   ↓
Display the top three matches
   ↓
Ask questions about one match
```

## 1. Start a session

The welcome page lets the user upload a CV or view the available jobs. The jobs page is
read-only and uses the same bundled job records as the matcher.

The upload route accepts text-based PDF and DOCX files up to 10 MB. It checks the actual file
type and rejects empty, damaged, encrypted, oversized, or unsupported documents before
processing begins.

An accepted upload creates unique IDs for the session, CV, and processing job. All temporary
artifacts for that visit are kept together under the session ID.

## 2. Read the CV

A document parser extracts the text. PDF text remains associated with its page, while DOCX
paragraphs and tables retain their original order. These source locations allow later facts
to be traced back to the CV.

The uploaded file is deleted after text extraction succeeds. The extracted text remains in
the temporary session until the remaining stages finish.

Scanned or image-only PDFs are not processed because the application does not currently
include optical character recognition.

## 3. Build an evidence-backed profile

The extracted text is sent to the language-model service in several small, structured
requests. It extracts:

- Employment experience
- Skills
- Qualifications and professional credentials
- Education
- Current country, when explicitly stated
- Current industry, when explicitly stated

The application places the current or most recent position first. The skill extraction step
reads the complete CV, including employment history and responsibilities. Degrees are placed
under Education; certifications, licences, and other formal non-degree awards are placed
under Qualifications.

Every proposed fact must refer to supporting text. The application checks that evidence
against the extracted document, stores an exact source excerpt, and removes unsupported
facts. Information that is not stated remains missing.

The resulting profile is read-only and is carried into the matching stage automatically.

## 4. Standardize the matching facts

The profile is reduced to five categories that also exist on every prepared job record.

### Education

Recognized education is converted to an ordered internal level aligned with the European
Qualifications Framework. During comparison, a higher recorded level can satisfy a lower
minimum requirement.

### Skills

Each extracted skill phrase is checked against the reviewed skills catalogue.

1. Known names and aliases are matched directly.
2. An embedding service compares the meaning of any unresolved phrase with catalogue
   descriptions.
3. A semantic mapping is accepted only when it passes the configured confidence and
   ambiguity checks.

Accepted skills use stable catalogue IDs. This allows different phrases in a CV and job
advert to resolve to the same skill. Weak or ambiguous phrases remain visible as unmapped
skills and cannot affect the result.

The catalogue uses reviewed ESCO and O*NET concepts plus clearly labelled local concepts
where a suitable standard entry is unavailable.

### Experience

Employment dates are converted to calendar-month intervals. Overlapping roles are merged so
the same month is counted once. The total can then be compared with a job's numeric minimum
when one is stated.

The current matcher treats total experience and relevant skills as separate facts. It does
not claim that every skill was used throughout the candidate's entire work history.

### Location

Location is reduced to an ISO country code. Detailed city, distance, remote-work, visa, and
relocation rules are not part of the comparison.

### Industry

An explicitly stated industry is mapped to a broad NAICS sector with a stable ID. The
application does not infer an industry from an employer name.

## 5. Load the standardized jobs

The bundled jobs have already passed through the same standardization rules. Their saved
records contain required and preferred facts, together with the catalogue versions used to
create them.

The matcher reads these prepared records directly. It does not ask the language model to
reinterpret every job when a CV is uploaded or when the API restarts. Job titles remain
display information and are not used as matching evidence.

## 6. Compare and rank

The application creates a temporary in-memory SQLite database for the match. Candidate facts
and job requirements are inserted using their standard keys.

Each job requirement receives one result:

- **Met** when the candidate has the same standard fact or meets an ordered threshold.
- **Missing** when no matching fact is present.

Free-text phrases do not enter this comparison. Skill IDs must be identical, education must
meet the ordered minimum, dated experience must meet the required number of months, and
country and industry IDs must match.

Each category is scored separately before the configured category weights are applied. If a
job does not contain a requirement for a category, that category is excluded and the
remaining weights are adjusted proportionally.

Required coverage determines the main ranking. Preferred coverage is considered next, and a
stable internal ID resolves an otherwise exact tie. All available jobs are ranked and the
highest three are returned.

## 7. Display the results

The results page shows the extracted profile and three compact job cards. The first match is
selected automatically. Selecting another card updates the detailed panel below it.

For the selected job, the page shows:

- Coverage for each matching category
- Met and Missing requirements
- Supporting excerpts from the CV
- Required and preferred totals
- Actions related to the documented gaps

Actions do not tell the user to claim experience they do not have. They can recommend adding
clearer CV evidence when the user genuinely has a missing skill or gaining the missing
experience, education, or credential.

A complete result means the standardized facts covered the recorded requirements. It is not
a guarantee of an interview, offer, or suitability decision.

## 8. Ask questions about a selected match

Each selected result includes a small career-assistant chat. When the user asks a question,
the browser sends the recent conversation and the selected match ID. The server verifies
that the match belongs to the current session, then builds a fresh system prompt containing:

- Standardized CV skills, education level, dated experience, country, and industry
- Extracted experience, education, and qualifications needed to explain the profile
- The selected job's standardized requirement keys and Met or Missing outcomes
- Category coverage, supporting evidence labels, and documented gap actions

The original CV text is not sent again. Strings from CV and job fields are treated as
untrusted data rather than instructions. The model must use only the supplied context, say
when information is missing, avoid inventing experience or credentials, and leave the
deterministic score unchanged.

The server returns one answer with a new UUID. It does not save questions or answers. The
browser keeps a separate conversation for each selected result in memory, limited to the
most recent exchanges sent with a new question.

## 9. Recover work and remove temporary data

While processing, the interface shows three stages:

`Reading your CV → Building your profile → Finding your matches`

The backend saves each completed stage atomically. If processing is interrupted, it checks
the saved artifacts and resumes from the next incomplete stage while the session remains
active. Temporary failures can be retried without repeating valid completed work.

The browser sends a heartbeat while the experience is open. Starting again deletes the
current session immediately. If the page closes, the browser crashes, or the connection is
lost, the heartbeat stops and the server removes the session after ten minutes of inactivity.

Deleted sessions cannot be recovered. The current application has no user accounts or saved
match history.

## 10. Future improvements

Before using the matcher beyond this proof of concept, the following improvements should be
made:

- **Match qualifications and licences:** Standardize required qualifications, certifications,
  and professional licences so regulated roles cannot match candidates who do not have the
  required credential.
- **Measure relevant experience:** Continue to ignore unreliable job titles, but connect years
  of experience to the skills or work domain in which that experience was gained. Unrelated
  employment time should not satisfy a role's experience requirement.
- **Strengthen evidence validation:** Verify score-driving details such as employment dates,
  current-role status, and country directly against the CV instead of relying only on a nearby
  title, company, or model-proposed quote.
- **Support common CV layouts:** Ground related information across adjacent paragraphs and
  table cells so a title, employer, and dates on separate lines still form one employment
  record.
- **Improve service readiness and uploads:** Keep new sessions queued while model services are
  starting, use controlled retry delays, align the web-server upload limit with the API's 10 MB
  limit, and return clear errors for documents that exceed the model's context capacity.

These changes preserve the current simple workflow while improving the accuracy, reliability,
and credibility of the matches.
