import { ChangeEvent, useEffect, useRef, useState } from "react";

type SessionStatus = "queued" | "processing" | "ready" | "failed" | "closing";
type ProcessingStage = "queued" | "reading_cv" | "building_profile" | "finding_matches" | "ready" | "failed";

interface SessionSummary {
  match_session_id: string;
  resume_id: string;
  ingest_job_id: string;
  status: SessionStatus;
  stage: ProcessingStage;
  attempt_count: number;
  expires_at: string;
  error: string | null;
}

interface EvidenceReference {
  block_id: string;
  quote: string;
}

interface CandidateExperience {
  experience_id: string;
  title: string;
  company: string;
  start_date: string | null;
  end_date: string | null;
  is_current: boolean;
  highlights: Array<{ text: string; evidence: EvidenceReference[] }>;
  evidence: EvidenceReference[];
}

interface CandidateProfile {
  profile_id: string;
  resume_id: string;
  featured_experience_id: string | null;
  experiences: CandidateExperience[];
  skills: Array<{ skill_id: string; name: string }>;
  standardized_skills: Array<{
    candidate_standard_skill_id: string;
    standard_skill_id: string;
    preferred_label: string;
    source: "esco" | "onet" | "job_matcher_extension";
    mapping_method: "exact_alias" | "vector";
    similarity: number;
    extracted_names: string[];
  }>;
  education_level: {
    education_level_id: string;
    level: "secondary" | "vocational" | "bachelors" | "masters" | "doctorate";
    eqf_level: number;
  } | null;
  country: {
    country_id: string;
    country_code: string;
    name: string;
  } | null;
  industry: {
    candidate_industry_id: string;
    industry_id: string;
    naics_code: string;
    preferred_label: string;
  } | null;
}

type MatchCategory = "education" | "skills" | "location" | "industry";
type RequirementStatus = "met" | "missing";

interface RequirementMatch {
  requirement_id: string;
  text: string;
  importance: "required" | "preferred";
  category: MatchCategory;
  status: RequirementStatus;
  evidence: Array<{ evidence_id: string; label: string }>;
  explanation: string;
  action: string | null;
}

interface JobMatch {
  match_result_id: string;
  title: string;
  company: string;
  summary: string;
  required_coverage_points: number;
  required_coverage_max: number;
  preferred_coverage_points: number;
  preferred_coverage_max: number;
  category_coverage: Array<{
    category: MatchCategory;
    met: number;
    missing: number;
  }>;
  requirements: RequirementMatch[];
}

interface MatchResults {
  top_matches: JobMatch[];
}

interface AvailableJob {
  job_id: string;
  title: string;
  company: string;
  summary: string;
  responsibilities: string[];
  required_qualifications: string[];
  preferred_qualifications: string[];
  minimum_education_level: "secondary" | "vocational" | "bachelors" | "masters" | "doctorate" | null;
  country_code: string;
  industry_label: string;
  location_label: string | null;
  work_pattern: string | null;
  employment_type: string | null;
  salary: string | null;
  source_url: string | null;
  source_checked_at: string | null;
}

type AppView = "home" | "jobs";

const stageCopy: Record<ProcessingStage, string> = {
  queued: "Preparing your CV",
  reading_cv: "Reading your CV",
  building_profile: "Building your profile",
  finding_matches: "Finding your matches",
  ready: "Your matches are ready",
  failed: "We couldn't process that CV",
};

const stagePosition: Record<ProcessingStage, number> = {
  queued: 0,
  reading_cv: 0,
  building_profile: 1,
  finding_matches: 2,
  ready: 2,
  failed: 0,
};

const categoryLabel: Record<MatchCategory, string> = {
  education: "Education",
  skills: "Skills",
  location: "Location",
  industry: "Industry",
};

const skillSourceLabel = {
  esco: "ESCO",
  onet: "O*NET",
  job_matcher_extension: "Local",
};

const educationLabel = {
  secondary: "Secondary education",
  vocational: "Vocational qualification",
  bachelors: "Bachelor's degree",
  masters: "Master's degree",
  doctorate: "Doctorate",
};

function countryName(countryCode: string) {
  try {
    return new Intl.DisplayNames(["en"], { type: "region" }).of(countryCode) ?? countryCode;
  } catch {
    return countryCode;
  }
}

function AvailableJobsPage({ onBack }: { onBack: () => void }) {
  const [jobs, setJobs] = useState<AvailableJob[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetch("/api/jobs")
      .then(async (response) => {
        if (!response.ok) throw new Error("The jobs list is unavailable right now");
        return (await response.json()) as AvailableJob[];
      })
      .then((availableJobs) => {
        if (!cancelled) setJobs(availableJobs);
      })
      .catch((reason) => {
        if (!cancelled) {
          setLoadError(reason instanceof Error ? reason.message : "The jobs list is unavailable right now");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const normalizedQuery = query.trim().toLocaleLowerCase();
  const filteredJobs = jobs.filter((job) => !normalizedQuery || [
    job.title,
    job.company,
    job.summary,
    job.location_label ?? "",
    job.industry_label,
    ...job.required_qualifications,
    ...job.preferred_qualifications,
  ].join(" ").toLocaleLowerCase().includes(normalizedQuery));

  return (
    <main className="shell jobs-shell">
      <section className="jobs-page">
        <header className="jobs-page-header">
          <div className="jobs-navigation">
            <div className="jobs-brand">
              <div className="mark" aria-hidden="true">JM</div>
              <span>Job Matcher</span>
            </div>
            <button className="back-button" type="button" onClick={onBack}>
              <span aria-hidden="true">←</span>
              Upload your CV
            </button>
          </div>
          <div className="jobs-hero">
            <p className="eyebrow">Available opportunities</p>
            <h1>Find your next role.</h1>
            <p>Browse every job currently included in Job Matcher, including ten roles sourced from live employer listings.</p>
          </div>
          <div className="job-search">
            <label htmlFor="job-search">Search jobs</label>
            <div className="job-search-input">
              <span aria-hidden="true">⌕</span>
              <input
                id="job-search"
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Job title, company, skill or industry"
                type="search"
                value={query}
              />
            </div>
          </div>
        </header>

        {loading && (
          <div className="jobs-loading" aria-live="polite">
            <span className="spinner small" aria-hidden="true" />
            Loading available jobs…
          </div>
        )}
        {loadError && <p className="error" role="alert">{loadError}</p>}
        {!loading && !loadError && (
          <div className="job-board">
            <div className="jobs-toolbar">
              <p><strong>{filteredJobs.length}</strong> {filteredJobs.length === 1 ? "job" : "jobs"}</p>
              <p><span className="source-dot" /> 10 live listings checked 23 August 2026</p>
            </div>
            {filteredJobs.length === 0 && (
              <div className="no-jobs">
                <h2>No matching jobs</h2>
                <p>Try a broader job title, company, skill, or industry.</p>
                <button type="button" onClick={() => setQuery("")}>Clear search</button>
              </div>
            )}
            <div className="available-jobs-list">
            {filteredJobs.map((job) => (
              <article className="available-job-card" key={job.job_id}>
                <header className="available-job-header">
                  <span className="company-mark" aria-hidden="true">{job.company.slice(0, 1)}</span>
                  <div className="available-job-title">
                    <div className="listing-labels">
                      <span>{job.source_url ? "Live listing" : "POC role"}</span>
                      {job.employment_type && <span>{job.employment_type}</span>}
                    </div>
                    <h2>{job.title}</h2>
                    <p className="job-byline">
                      <strong>{job.company}</strong>
                      <span>·</span>
                      {job.location_label ?? countryName(job.country_code)}
                    </p>
                  </div>
                </header>
                <p className="available-job-summary">{job.summary}</p>
                <div className="job-facts" aria-label="Job summary details">
                  {job.salary && <span>{job.salary}</span>}
                  {job.work_pattern && <span>{job.work_pattern}</span>}
                  <span>{job.industry_label}</span>
                </div>
                <details className="job-details">
                  <summary>View job details <span aria-hidden="true">+</span></summary>
                  <div className="job-information-grid">
                    <section>
                      <h3>What you would do</h3>
                      <ul>{job.responsibilities.map((item) => <li key={item}>{item}</li>)}</ul>
                    </section>
                    <section>
                      <h3>Required experience</h3>
                      <ul>{job.required_qualifications.map((item) => <li key={item}>{item}</li>)}</ul>
                    </section>
                    <section>
                      <h3>Preferred experience</h3>
                      <ul>{job.preferred_qualifications.map((item) => <li key={item}>{item}</li>)}</ul>
                    </section>
                  </div>
                  <div className="job-details-footer">
                    <span>{job.minimum_education_level
                      ? educationLabel[job.minimum_education_level]
                      : "No degree requirement stated"}</span>
                    {job.source_url && (
                      <a href={job.source_url} target="_blank" rel="noreferrer">
                        View original listing <span aria-hidden="true">↗</span>
                      </a>
                    )}
                  </div>
                </details>
              </article>
            ))}
            </div>
          </div>
        )}
      </section>
    </main>
  );
}

export default function App() {
  const [view, setView] = useState<AppView>(() => (
    window.location.pathname.startsWith("/jobs") ? "jobs" : "home"
  ));
  const [session, setSession] = useState<SessionSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<CandidateProfile | null>(null);
  const [results, setResults] = useState<MatchResults | null>(null);
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [restoringSession, setRestoringSession] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleHistoryChange = () => {
      setView(window.location.pathname.startsWith("/jobs") ? "jobs" : "home");
    };
    window.addEventListener("popstate", handleHistoryChange);
    return () => window.removeEventListener("popstate", handleHistoryChange);
  }, []);

  useEffect(() => {
    const sessionId = sessionStorage.getItem("job-matcher-session");
    if (!sessionId) {
      setRestoringSession(false);
      return;
    }

    let cancelled = false;
    void fetch(`/api/match-sessions/${sessionId}/heartbeat`, { method: "POST" })
      .then(async (response) => {
        if (!response.ok) throw new Error("Session is no longer available");
        return (await response.json()) as SessionSummary;
      })
      .then((activeSession) => {
        if (!cancelled) setSession(activeSession);
      })
      .catch(() => {
        sessionStorage.removeItem("job-matcher-session");
      })
      .finally(() => {
        if (!cancelled) setRestoringSession(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!session) return;
    sessionStorage.setItem("job-matcher-session", session.match_session_id);

    const heartbeat = window.setInterval(() => {
      void fetch(`/api/match-sessions/${session.match_session_id}/heartbeat`, { method: "POST" });
    }, 20_000);

    return () => {
      window.clearInterval(heartbeat);
    };
  }, [session?.match_session_id]);

  useEffect(() => {
    if (!session || session.status === "ready") return;
    const events = new EventSource(`/api/match-sessions/${session.match_session_id}/events`);
    events.addEventListener("status", (event) => {
      setSession(JSON.parse((event as MessageEvent).data) as SessionSummary);
    });
    events.addEventListener("closed", () => {
      events.close();
      sessionStorage.removeItem("job-matcher-session");
      setSession(null);
      setProfile(null);
      setResults(null);
      setSelectedMatchId(null);
    });
    events.onerror = () => undefined;
    return () => events.close();
  }, [session?.match_session_id, session?.status]);

  useEffect(() => {
    if (!session || profile || !["finding_matches", "ready"].includes(session.stage)) return;
    let cancelled = false;
    void fetch(`/api/match-sessions/${session.match_session_id}/profile`)
      .then(async (response) => {
        if (!response.ok) throw new Error("Profile is not ready");
        return (await response.json()) as CandidateProfile;
      })
      .then((candidateProfile) => {
        if (!cancelled) setProfile(candidateProfile);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [session?.match_session_id, session?.stage, profile]);

  useEffect(() => {
    if (!session || results || session.stage !== "ready") return;
    let cancelled = false;
    void fetch(`/api/match-sessions/${session.match_session_id}/results`)
      .then(async (response) => {
        if (!response.ok) throw new Error("Match results are not ready");
        return (await response.json()) as MatchResults;
      })
      .then((matchResults) => {
        if (!cancelled) setResults(matchResults);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [session?.match_session_id, session?.stage, results]);

  async function resetSession() {
    if (session) {
      try {
        await fetch(`/api/match-sessions/${session.match_session_id}/close`, {
          method: "POST",
          headers: { "X-Job-Matcher-Close-Reason": "user-reset" },
        });
      } finally {
        sessionStorage.removeItem("job-matcher-session");
        setSession(null);
        setProfile(null);
        setResults(null);
        setSelectedMatchId(null);
        if (inputRef.current) inputRef.current.value = "";
      }
    }
  }

  async function retrySession() {
    if (!session) return;
    setError(null);
    const response = await fetch(`/api/match-sessions/${session.match_session_id}/retry`, {
      method: "POST",
    });
    if (!response.ok) {
      const payload = (await response.json()) as { detail?: string };
      setError(payload.detail ?? "We couldn't retry this match");
      return;
    }
    setSession((await response.json()) as SessionSummary);
  }

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    const form = new FormData();
    form.append("resume", file);
    try {
      const response = await fetch("/api/match-sessions", { method: "POST", body: form });
      if (!response.ok) {
        const payload = (await response.json()) as { detail?: string };
        throw new Error(payload.detail ?? "Upload failed");
      }
      setSession((await response.json()) as SessionSummary);
      setProfile(null);
      setResults(null);
      setSelectedMatchId(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) void upload(file);
  }

  function navigateTo(nextView: AppView) {
    const nextPath = nextView === "jobs" ? "/jobs" : "/";
    if (window.location.pathname !== nextPath) window.history.pushState({}, "", nextPath);
    setView(nextView);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  if (view === "jobs") {
    return <AvailableJobsPage onBack={() => navigateTo("home")} />;
  }

  if (session) {
    if (session.status === "failed") {
      return (
        <main className="shell">
          <section className="processing-card" aria-live="polite">
            <div className="mark" aria-hidden="true">JM</div>
            <p className="eyebrow">Job Matcher</p>
            <h1>We couldn't finish that match.</h1>
            <p className="supporting">{session.error ?? "Please try a different PDF or DOCX file."}</p>
            {error && <p className="error">{error}</p>}
            <div className="retry-actions">
              <button className="primary" onClick={() => void retrySession()}>
                Try again
                <span aria-hidden="true">↗</span>
              </button>
              <button className="text-button" onClick={() => void resetSession()}>
                Use another CV
              </button>
            </div>
          </section>
        </main>
      );
    }

    if (profile) {
      const featured = profile.experiences.find(
        (experience) => experience.experience_id === profile.featured_experience_id,
      ) ?? profile.experiences[0];
      const mappedNames = new Set(
        profile.standardized_skills.flatMap((skill) =>
          skill.extracted_names.map((name) => name.toLocaleLowerCase()),
        ),
      );
      const unmappedSkills = profile.skills.filter(
        (skill) => !mappedNames.has(skill.name.toLocaleLowerCase()),
      );
      const selectedMatch = results?.top_matches.find(
        (match) => match.match_result_id === selectedMatchId,
      ) ?? results?.top_matches[0] ?? null;
      const selectedMatchRank = selectedMatch
        ? results?.top_matches.findIndex(
          (match) => match.match_result_id === selectedMatch.match_result_id,
        ) ?? -1
        : -1;
      return (
        <main className="shell profile-shell">
          <section className="profile-card" aria-live="polite">
            <header className="profile-header">
              <div className="mark" aria-hidden="true">JM</div>
              <div className="matching-status">
                {!results && <span className="spinner small" aria-hidden="true" />}
                {results ? "Your top three matches" : "Finding your top three jobs"}
              </div>
            </header>
            <p className="eyebrow">Your extracted profile</p>
            <h1>{featured?.title ?? "Your experience"}</h1>
            {featured && <p className="current-company">{featured.company}</p>}
            <p className="profile-note">Standardized, read-only, and based only on evidence in your CV.</p>

            <div className="profile-grid">
              <section className="profile-section">
                <h2>Education level</h2>
                {profile.education_level ? (
                  <>
                    <h3>{educationLabel[profile.education_level.level]}</h3>
                    <p>EQF level {profile.education_level.eqf_level}</p>
                  </>
                ) : <p>Not stated in this CV.</p>}
              </section>

              <section className="profile-section">
                <h2>Standardized skills</h2>
                {profile.standardized_skills.length ? (
                  <div className="chips">
                    {profile.standardized_skills.map((skill) => (
                      <span key={skill.candidate_standard_skill_id}>
                        {skill.preferred_label}
                        <small>
                          {skillSourceLabel[skill.source]} · {skill.mapping_method === "vector"
                            ? `Vector ${Math.round(skill.similarity * 100)}%`
                            : "Exact"}
                        </small>
                      </span>
                    ))}
                  </div>
                ) : <p>No catalogue skills found.</p>}
                {unmappedSkills.length > 0 && (
                  <>
                    <p className="mapping-note">Extracted but not confidently mapped</p>
                    <div className="chips unmapped">
                      {unmappedSkills.map((skill) => (
                        <span key={skill.skill_id}>{skill.name}</span>
                      ))}
                    </div>
                  </>
                )}
              </section>

              <section className="profile-section">
                <h2>Location</h2>
                {profile.country ? (
                  <>
                    <h3>{profile.country.name}</h3>
                    <p>ISO country code {profile.country.country_code}</p>
                  </>
                ) : <p>Not stated in this CV.</p>}
              </section>

              <section className="profile-section">
                <h2>Industry</h2>
                {profile.industry ? (
                  <>
                    <h3>{profile.industry.preferred_label}</h3>
                    <p>NAICS sector {profile.industry.naics_code}</p>
                  </>
                ) : <p>Not stated or not mapped.</p>}
              </section>
            </div>
            {results && (
              <section className="results-section">
                <div className="results-intro">
                  <div className="results-heading">
                    <p className="eyebrow">Your matches</p>
                    <h2>Your best matches, side by side.</h2>
                    <p>Select a role to see exactly where your CV matches and what could strengthen it.</p>
                  </div>
                  <button className="restart-button" type="button" onClick={() => void resetSession()}>
                    Match another CV
                  </button>
                </div>
                <div className="match-selector" aria-label="Your top three job matches">
                  {results.top_matches.map((match, index) => {
                    const gaps = match.requirements.filter((item) => item.status !== "met");
                    const isSelected = match.match_result_id === selectedMatch?.match_result_id;
                    return (
                      <button
                        aria-controls="selected-match-detail"
                        aria-pressed={isSelected}
                        className={`match-summary-card ${isSelected ? "selected" : ""}`}
                        key={match.match_result_id}
                        onClick={() => setSelectedMatchId(match.match_result_id)}
                        type="button"
                      >
                        <span className="match-summary-top">
                          <span className="rank">{index + 1}</span>
                          <span className="match-position">
                            {index === 0 ? "Top match" : `Match ${index + 1}`}
                          </span>
                        </span>
                        <span className="match-summary-title">{match.title}</span>
                        <span className="match-company">{match.company}</span>
                        <span className="match-summary-copy">{match.summary}</span>
                        <span className="match-summary-metrics">
                          <span>
                            <strong>{match.required_coverage_points}/{match.required_coverage_max}</strong>
                            required
                          </span>
                          <span>
                            <strong>{match.preferred_coverage_points}/{match.preferred_coverage_max}</strong>
                            preferred
                          </span>
                        </span>
                        <span className="match-summary-footer">
                          {gaps.length === 0
                            ? "No documented gaps"
                            : `${gaps.length} ${gaps.length === 1 ? "area" : "areas"} to strengthen`}
                          <span aria-hidden="true">→</span>
                        </span>
                      </button>
                    );
                  })}
                </div>

                {selectedMatch && (() => {
                  const met = selectedMatch.requirements.filter((item) => item.status === "met");
                  const gaps = selectedMatch.requirements.filter((item) => item.status !== "met");
                  return (
                    <article className="match-detail" id="selected-match-detail" aria-live="polite">
                      <header className="match-detail-header">
                        <div className="match-title-row">
                          <span className="rank">{selectedMatchRank + 1}</span>
                          <div>
                            <p className="selected-label">Selected match</p>
                            <h3>{selectedMatch.title}</h3>
                            <p className="match-company">{selectedMatch.company}</p>
                          </div>
                        </div>
                        <p className="match-summary">{selectedMatch.summary}</p>
                      </header>

                        <div className="coverage-grid" aria-label="Coverage for the selected job">
                          <div>
                            <span>Required</span>
                            <strong>{selectedMatch.required_coverage_points} of {selectedMatch.required_coverage_max} matched</strong>
                          </div>
                          <div>
                            <span>Preferred</span>
                            <strong>{selectedMatch.preferred_coverage_points} of {selectedMatch.preferred_coverage_max} matched</strong>
                          </div>
                          {selectedMatch.category_coverage.map((coverage) => (
                            <div key={coverage.category}>
                              <span>{categoryLabel[coverage.category]}</span>
                              <strong>{coverage.met} met · {coverage.missing} missing</strong>
                            </div>
                          ))}
                        </div>

                        <div className="requirement-columns">
                          <section>
                            <h4>What lines up</h4>
                            <p className="column-note">Open an item to see the evidence from your CV.</p>
                            {met.length ? met.map((item) => (
                              <details className="requirement met" key={item.requirement_id}>
                                <summary><span>Met</span>{item.text}</summary>
                                <p>{item.explanation}</p>
                                {item.evidence.map((evidence) => <small key={evidence.evidence_id}>CV evidence: {evidence.label}</small>)}
                              </details>
                            )) : <p className="empty-state">No fully evidenced requirements yet.</p>}
                          </section>
                          <section>
                            <h4>Ways to strengthen the match</h4>
                            <p className="column-note">Open an item to see the gap and a suggested next step.</p>
                            {gaps.length ? gaps.map((item) => (
                              <details className={`requirement ${item.status}`} key={item.requirement_id}>
                                <summary><span>Gap</span>{item.text}</summary>
                                <p>{item.explanation}</p>
                                {item.action && <small>Action: {item.action}</small>}
                              </details>
                            )) : <p className="empty-state">All documented requirements are evidenced.</p>}
                          </section>
                        </div>
                    </article>
                  );
                })()}
              </section>
            )}
            <p className="fine-print">Your temporary profile is automatically deleted after you leave.</p>
            <p className="data-credit">Includes information from the O*NET 30.3 Database by the U.S. Department of Labor, Employment and Training Administration. Used under CC BY 4.0.</p>
          </section>
        </main>
      );
    }

    return (
      <main className="shell">
        <section className="processing-card" aria-live="polite">
          <div className="spinner" aria-hidden="true" />
          <p className="eyebrow">Job Matcher</p>
          <h1>{stageCopy[session.stage]}</h1>
          <p className="supporting">We keep your CV only for this matching session.</p>
          <div className="steps" aria-label="Processing progress">
            {["Reading your CV", "Building your profile", "Finding your matches"].map((label, index) => (
              <div className={`step ${index === stagePosition[session.stage] ? "active" : ""}`} key={label}>
                <span>{index + 1}</span>{label}
              </div>
            ))}
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="shell">
      <section className="welcome-card">
        <div className="mark" aria-hidden="true">JM</div>
        <p className="eyebrow">Private by design</p>
        <h1>Welcome to<br />Job Matcher.</h1>
        <p className="intro">Upload your CV and see the three roles that align best with your experience.</p>
        <input ref={inputRef} className="visually-hidden" type="file" accept=".pdf,.docx" onChange={handleFile} />
        <div className="welcome-actions">
          <button className="primary" disabled={uploading || restoringSession} onClick={() => inputRef.current?.click()}>
            {uploading ? "Uploading…" : restoringSession ? "Checking session…" : "Upload your resume"}
            <span aria-hidden="true">↗</span>
          </button>
          <button className="secondary-action" type="button" onClick={() => navigateTo("jobs")}>
            View available jobs
            <span aria-hidden="true">→</span>
          </button>
        </div>
        <p className="fine-print">PDF or DOCX · Temporary and automatically deleted</p>
        {error && <p className="error" role="alert">{error}</p>}
      </section>
    </main>
  );
}
