import { useEffect, useMemo, useState } from "react";
import {
  Badge,
  Btn,
  COORDINATOR_CODES,
  Empty,
  ErrorBox,
  Loading,
  Metric,
  Notice,
  Title,
  hasRole,
  initials,
  send,
  useAction,
  useApi,
  useCoursePicker,
} from "./shared";

export type Learner = {
  student_id: string;
  name: string;
  email: string | null;
  progress_pct: number;
  attendance_id: string | null;
  sessions_present: number;
  sessions_total: number;
  attendance_pct: number | null;
  avg_score: number | null;
  attempts: number;
  eligible: boolean;
};
export type Roster = {
  course: { id: string; title: string };
  attendance_threshold_pct: number;
  pass_mark: number;
  learners: Learner[];
};

const STATUSES = ["present", "late", "absent", "excused"] as const;

function downloadCsv(name: string, rows: (string | number | null)[][]) {
  const text = rows.map((row) => row.map((cell) => `"${String(cell ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

/** Attendance register: record a session for the enrolled roster and apply audited corrections. */
export function LiveAttendance() {
  const { courseId, picker } = useCoursePicker();
  const roster = useApi<Roster>(courseId ? `/api/v1/roster?course_id=${courseId}` : null);
  const [marks, setMarks] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<Learner | null>(null);
  const [present, setPresent] = useState(0);
  const [total, setTotal] = useState(0);
  const [reason, setReason] = useState("");
  const action = useAction();
  const canCorrect = hasRole(...COORDINATOR_CODES);

  useEffect(() => {
    setMarks({});
    setEditing(null);
  }, [courseId]);

  const learners = roster.data?.learners ?? [];
  const below = learners.filter((l) => l.attendance_pct !== null && l.attendance_pct < (roster.data?.attendance_threshold_pct ?? 75));
  const markFor = (id: string) => marks[id] ?? "present";

  return (
    <div className="page-stack">
      <Title
        tag="ATTENDANCE · LIVE REGISTER"
        title="Attendance Management"
        copy="Record a session for the enrolled roster. Corrections keep the original value, reason and editor in the audit trail."
        actions={
          <Btn
            disabled={!learners.length || action.busy}
            onClick={() =>
              action.run(async () => {
                const result = await send<{ recorded: number }>("POST", "/api/v1/attendance/record", {
                  course_id: courseId,
                  entries: learners.map((l) => ({ student_id: l.student_id, status: markFor(l.student_id) })),
                });
                setMarks({});
                roster.reload();
                return `Recorded attendance for ${result.recorded} learners.`;
              })
            }
            variant="primary"
          >
            {action.busy ? "Saving..." : "Record session"}
          </Btn>
        }
      />
      <div className="card form-grid">{picker}</div>
      <Notice text={action.ok} tone="success" />
      <Notice text={action.fail} tone="danger" />
      <div className="kpi-grid compact">
        <Metric label="ENROLLED LEARNERS" value={learners.length} />
        <Metric label={`BELOW ${roster.data?.attendance_threshold_pct ?? 75}%`} value={below.length} note="Needs follow-up" />
        <Metric
          label="AVERAGE ATTENDANCE"
          value={
            learners.filter((l) => l.attendance_pct !== null).length
              ? `${(learners.reduce((sum, l) => sum + (l.attendance_pct ?? 0), 0) / learners.filter((l) => l.attendance_pct !== null).length).toFixed(1)}%`
              : "No sessions"
          }
        />
      </div>
      {roster.loading ? <Loading what="roster" /> : null}
      {roster.error ? <ErrorBox message={roster.error} onRetry={roster.reload} /> : null}
      {!roster.loading && !roster.error && !learners.length ? (
        <Empty title="No enrolled learners" hint="Enroll learners in this course (or add them to a cohort) to take attendance." />
      ) : null}
      {learners.length ? (
        <section className="card coordinator-table">
          <div className="section-head">
            <div>
              <span className="eyebrow">{(roster.data?.course.title ?? "").toUpperCase()}</span>
              <h2>Session register</h2>
            </div>
            <Badge>{learners.length} LEARNERS</Badge>
          </div>
          {learners.map((learner) => (
            <div className="attendance-grid-row" key={learner.student_id}>
              <span className="student-cell">
                <span className="avatar avatar-0">{initials(learner.name)}</span>
                <strong>{learner.name}</strong>
              </span>
              <span>
                {learner.attendance_pct === null ? "No sessions yet" : `${learner.attendance_pct}% (${learner.sessions_present}/${learner.sessions_total})`}
              </span>
              <select
                aria-label={`Status for ${learner.name}`}
                value={markFor(learner.student_id)}
                onChange={(event) => setMarks({ ...marks, [learner.student_id]: event.target.value })}
              >
                {STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
              {canCorrect && learner.attendance_id ? (
                <Btn
                  onClick={() => {
                    setEditing(learner);
                    setPresent(learner.sessions_present);
                    setTotal(learner.sessions_total);
                    setReason("");
                  }}
                >
                  Correct
                </Btn>
              ) : (
                <span />
              )}
            </div>
          ))}
        </section>
      ) : null}
      {editing ? (
        <section className="card correction-panel">
          <span className="eyebrow">AUDITED CORRECTION</span>
          <h2>{editing.name}</h2>
          <label>
            Sessions present
            <input type="number" min={0} value={present} onChange={(event) => setPresent(Number(event.target.value))} />
          </label>
          <label>
            Sessions total
            <input type="number" min={0} value={total} onChange={(event) => setTotal(Number(event.target.value))} />
          </label>
          <label>
            Mandatory reason (min 8 characters)
            <textarea value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Explain why this record is being corrected..." />
          </label>
          <div className="row-actions">
            <Btn onClick={() => setEditing(null)}>Cancel</Btn>
            <Btn
              variant="primary"
              disabled={reason.trim().length < 8 || action.busy}
              onClick={() =>
                action.run(async () => {
                  await send("PATCH", `/api/v1/attendance/${editing.attendance_id}`, {
                    sessions_present: present,
                    sessions_total: total,
                    reason: reason.trim(),
                  });
                  setEditing(null);
                  roster.reload();
                  return `Correction recorded for ${editing.name}.`;
                })
              }
            >
              Save audited correction
            </Btn>
          </div>
        </section>
      ) : null}
    </div>
  );
}

/** Roster / gradebook summary used for batch management and the gradebook. */
export function LiveRoster({ variant }: { variant: "batch" | "gradebook" }) {
  const { courseId, picker } = useCoursePicker();
  const roster = useApi<Roster>(courseId ? `/api/v1/roster?course_id=${courseId}` : null);
  const learners = roster.data?.learners ?? [];
  const eligible = learners.filter((l) => l.eligible).length;
  const scored = learners.filter((l) => l.avg_score !== null);
  const average = scored.length ? scored.reduce((sum, l) => sum + (l.avg_score ?? 0), 0) / scored.length : null;

  return (
    <div className="page-stack">
      <Title
        tag={variant === "batch" ? "COORDINATOR · ASSIGNED SCOPE" : "GRADEBOOK · LIVE"}
        title={variant === "batch" ? "Student & Batch Management" : "Gradebook"}
        copy={
          variant === "batch"
            ? "Enrolled learners with progress, attendance and score signals for the selected course."
            : "Average assessment scores, attendance and eligibility per learner. Scores are percentages (0-100)."
        }
        actions={
          <Btn
            disabled={!learners.length}
            onClick={() =>
              downloadCsv("roster.csv", [
                ["Name", "Email", "Progress %", "Attendance %", "Avg score %", "Attempts", "Eligible"],
                ...learners.map((l) => [l.name, l.email, l.progress_pct, l.attendance_pct, l.avg_score, l.attempts, l.eligible ? "yes" : "review"]),
              ])
            }
          >
            Export CSV
          </Btn>
        }
      />
      <div className="card form-grid">{picker}</div>
      <div className="kpi-grid compact">
        <Metric label="LEARNERS" value={learners.length} />
        <Metric label="ELIGIBLE" value={`${eligible}/${learners.length}`} note={`Pass mark ${roster.data?.pass_mark ?? 60}% · attendance ${roster.data?.attendance_threshold_pct ?? 75}%`} />
        <Metric label="AVERAGE SCORE" value={average === null ? "No scores" : `${average.toFixed(1)}%`} />
      </div>
      {roster.loading ? <Loading what="roster" /> : null}
      {roster.error ? <ErrorBox message={roster.error} onRetry={roster.reload} /> : null}
      {!roster.loading && !roster.error && !learners.length ? <Empty title="No enrolled learners for this course" /> : null}
      {learners.length ? (
        <section className="card coordinator-table">
          {learners.map((l) => (
            <div className="batch-student-row" key={l.student_id}>
              <span className="student-cell">
                <span className="avatar avatar-1">{initials(l.name)}</span>
                <span>
                  <strong>{l.name}</strong>
                  <small>{l.email ?? ""}</small>
                </span>
              </span>
              <span>
                <small>PROGRESS</small>
                <strong>{l.progress_pct}%</strong>
              </span>
              <span>
                <small>ATTENDANCE</small>
                <strong>{l.attendance_pct === null ? "—" : `${l.attendance_pct}%`}</strong>
              </span>
              <span>
                <small>AVG SCORE</small>
                <strong>{l.avg_score === null ? "—" : `${l.avg_score}%`}</strong>
              </span>
              <Badge tone={l.eligible ? "success" : "warning"}>{l.eligible ? "ELIGIBLE" : "REVIEW"}</Badge>
            </div>
          ))}
        </section>
      ) : null}
    </div>
  );
}

type AssessmentRow = { id: string; title: string; course_id: string; proctored: boolean };
type Result = { id: string; assessment_id: string; student_id: string; score: number | null; status: string; published: boolean };

/** Result verification: audited score changes, scorecard submission and approval. */
export function LiveScores() {
  const { courseId, picker } = useCoursePicker();
  const assessments = useApi<AssessmentRow[]>(courseId ? `/api/v1/assessments?course_id=${courseId}` : null);
  const roster = useApi<Roster>(courseId ? `/api/v1/roster?course_id=${courseId}` : null);
  const [assessmentId, setAssessmentId] = useState("");
  const results = useApi<Result[]>(assessmentId ? `/api/v1/results?assessment_id=${assessmentId}` : null);
  const [edits, setEdits] = useState<Record<string, { score: string; reason: string }>>({});
  const [scorecardId, setScorecardId] = useState("");
  const action = useAction();

  useEffect(() => {
    const first = assessments.data?.[0]?.id ?? "";
    setAssessmentId((current) => (assessments.data?.some((a) => a.id === current) ? current : first));
    setScorecardId("");
  }, [assessments.data]);

  const names = useMemo(() => new Map((roster.data?.learners ?? []).map((l) => [l.student_id, l.name])), [roster.data]);
  const rows = results.data ?? [];
  const published = rows.filter((r) => r.published).length;

  return (
    <div className="page-stack">
      <Title
        tag="COORDINATOR · AUDITED MARKS"
        title="Assessment Score Management"
        copy="Review attempt scores, make audited adjustments and publish a scorecard for the selected course."
      />
      <div className="card form-grid">
        {picker}
        <label>
          Assessment
          <select value={assessmentId} onChange={(event) => setAssessmentId(event.target.value)}>
            {(assessments.data ?? []).map((a) => (
              <option key={a.id} value={a.id}>
                {a.title}
              </option>
            ))}
          </select>
        </label>
      </div>
      <Notice text={action.ok} tone="success" />
      <Notice text={action.fail} tone="danger" />
      <div className="kpi-grid compact">
        <Metric label="ATTEMPTS" value={rows.length} />
        <Metric label="PUBLISHED" value={`${published}/${rows.length}`} note="Visible to learners and parents" />
        <Metric label="PASS MARK" value={`${roster.data?.pass_mark ?? 60}%`} />
      </div>
      {assessments.error ? <ErrorBox message={assessments.error} onRetry={assessments.reload} /> : null}
      {results.loading ? <Loading what="results" /> : null}
      {results.error ? <ErrorBox message={results.error} onRetry={results.reload} /> : null}
      {!assessments.loading && !assessments.data?.length ? <Empty title="No assessments for this course" hint="Teachers can build one from the approved question bank." /> : null}
      {assessmentId && !results.loading && !results.error && !rows.length ? <Empty title="No attempts yet" /> : null}
      {rows.length ? (
        <section className="card coordinator-table">
          <div className="score-grid-row head">
            <span>Learner</span>
            <span>Status</span>
            <span>Score %</span>
            <span>Revised score</span>
            <span>Reason</span>
            <span />
          </div>
          {rows.map((row) => {
            const edit = edits[row.id] ?? { score: "", reason: "" };
            const valid = edit.score !== "" && Number(edit.score) >= 0 && Number(edit.score) <= 100 && edit.reason.trim().length >= 8;
            return (
              <div className="score-grid-row" key={row.id}>
                <span className="student-cell">
                  <span className="avatar avatar-2">{initials(names.get(row.student_id) ?? "?")}</span>
                  <strong>{names.get(row.student_id) ?? row.student_id.slice(0, 8)}</strong>
                </span>
                <Badge tone={row.published ? "success" : row.status === "adjusted" ? "warning" : "default"}>
                  {row.published ? "PUBLISHED" : row.status.toUpperCase()}
                </Badge>
                <strong>{row.score ?? "—"}</strong>
                <input
                  aria-label="Revised score"
                  type="number"
                  min={0}
                  max={100}
                  value={edit.score}
                  onChange={(event) => setEdits({ ...edits, [row.id]: { ...edit, score: event.target.value } })}
                />
                <input
                  aria-label="Reason for change"
                  placeholder="Reason (min 8 chars)"
                  value={edit.reason}
                  onChange={(event) => setEdits({ ...edits, [row.id]: { ...edit, reason: event.target.value } })}
                />
                <Btn
                  disabled={!valid || action.busy}
                  onClick={() =>
                    action.run(async () => {
                      await send("POST", `/api/v1/results/${row.id}/adjust`, { revised_score: Number(edit.score), reason: edit.reason.trim() });
                      setEdits({ ...edits, [row.id]: { score: "", reason: "" } });
                      results.reload();
                      return "Score adjustment recorded with reason and editor.";
                    })
                  }
                >
                  Save
                </Btn>
              </div>
            );
          })}
        </section>
      ) : null}
      {rows.length ? (
        <section className="card score-audit-editor">
          <div>
            <span className="eyebrow">CONTROLLED PUBLICATION</span>
            <h2>{scorecardId ? "Scorecard awaiting approval" : "Submit scorecard"}</h2>
            <p>Publishing makes every attempt for this course visible to the learner and linked parents.</p>
          </div>
          {!scorecardId ? (
            <Btn
              variant="primary"
              disabled={action.busy}
              onClick={() =>
                action.run(async () => {
                  const card = await send<{ id: string }>("POST", "/api/v1/scorecards", { course_id: courseId, payload: { assessment_id: assessmentId } });
                  setScorecardId(card.id);
                  return "Scorecard submitted for approval.";
                })
              }
            >
              Submit for approval
            </Btn>
          ) : (
            <Btn
              variant="primary"
              disabled={action.busy}
              onClick={() =>
                action.run(async () => {
                  const done = await send<{ attempts_published: number }>("POST", `/api/v1/scorecards/${scorecardId}/approve`);
                  setScorecardId("");
                  results.reload();
                  return `Published ${done.attempts_published} attempts.`;
                })
              }
            >
              Approve & publish
            </Btn>
          )}
        </section>
      ) : null}
    </div>
  );
}

type AssignmentRow = {
  id: string;
  course_id: string;
  title: string;
  instructions: string;
  status: string;
  max_score: number;
  due_at?: string | null;
  submission_count?: number;
  submission?: { id: string; status: string; score: number | null; feedback: string; submitted_at?: string | null; attachment_name?: string } | null;
};
type SubmissionRow = { id: string; student_name: string; body: string; status: string; score: number | null; feedback: string; submitted_at?: string | null; attachment_name?: string };

/** Assignments for learners (submit, see feedback) and staff (create, review, grade). */
export function LiveAssignments() {
  const learnerOnly = hasRole("student") && !hasRole("teacher", "coordinator", "corporate_trainer", "institution_admin", "principal_academic_director");
  const canAuthor = hasRole("teacher", "corporate_trainer", "content_reviewer", "institution_admin");
  const { courseId, picker } = useCoursePicker();
  const list = useApi<AssignmentRow[]>(courseId ? `/api/v1/assignments?course_id=${courseId}` : null);
  const [title, setTitle] = useState("");
  const [instructions, setInstructions] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [open, setOpen] = useState("");
  const submissions = useApi<SubmissionRow[]>(open && !learnerOnly ? `/api/v1/assignments/${open}/submissions` : null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [files, setFiles] = useState<Record<string, { name: string; text: string }>>({});
  const [grades, setGrades] = useState<Record<string, { score: string; feedback: string }>>({});
  const action = useAction();

  return (
    <div className="page-stack">
      <Title
        tag={learnerOnly ? "MY ASSIGNMENTS" : "ASSIGNMENTS · LIVE"}
        title={learnerOnly ? "Assignments" : "Assignment Management"}
        copy={learnerOnly ? "Assignments for the courses you are enrolled in." : "Create assignments, review submissions and grade with feedback."}
      />
      <div className="card form-grid">{picker}</div>
      <Notice text={action.ok} tone="success" />
      <Notice text={action.fail} tone="danger" />
      {canAuthor ? (
        <section className="card form-grid">
          <label>
            Title
            <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Assignment title" />
          </label>
          <label>
            Instructions
            <textarea value={instructions} onChange={(event) => setInstructions(event.target.value)} />
          </label>
          <label>
            Due date
            <input type="datetime-local" value={dueAt} onChange={(event) => setDueAt(event.target.value)} />
          </label>
          <Btn
            variant="primary"
            disabled={title.trim().length < 3 || !courseId || action.busy}
            onClick={() =>
              action.run(async () => {
                await send("POST", "/api/v1/assignments", {
                  course_id: courseId,
                  title: title.trim(),
                  instructions,
                  due_at: dueAt ? new Date(dueAt).toISOString() : null,
                });
                setTitle("");
                setInstructions("");
                setDueAt("");
                list.reload();
                return "Assignment published to enrolled learners.";
              })
            }
          >
            Create assignment
          </Btn>
        </section>
      ) : null}
      {list.loading ? <Loading what="assignments" /> : null}
      {list.error ? <ErrorBox message={list.error} onRetry={list.reload} /> : null}
      {!list.loading && !list.error && !(list.data ?? []).length ? <Empty title="No assignments for this course" /> : null}
      {(list.data ?? []).map((item) => (
        <section className="card" key={item.id}>
          <div className="section-head">
            <div>
              <span className="eyebrow">MAX {item.max_score}</span>
              <h2>{item.title}</h2>
              <p>{item.instructions || "No instructions provided."}</p>
              {item.due_at ? <small>Due {new Date(item.due_at).toLocaleString()}</small> : null}
            </div>
            {learnerOnly ? (
              <Badge tone={item.submission ? (item.submission.status === "graded" ? "success" : "ai") : "warning"}>
                {item.submission ? item.submission.status.toUpperCase() : "NOT SUBMITTED"}
              </Badge>
            ) : (
              <Btn onClick={() => setOpen(open === item.id ? "" : item.id)}>{item.submission_count ?? 0} submissions</Btn>
            )}
          </div>
          {learnerOnly && item.submission?.score != null ? (
            <p>
              Score {item.submission.score}/{item.max_score}. {item.submission.feedback}
            </p>
          ) : null}
          {learnerOnly && item.submission?.submitted_at ? <small>Submitted {new Date(item.submission.submitted_at).toLocaleString()}{item.submission.attachment_name ? ` · ${item.submission.attachment_name}` : ""}</small> : null}
          {learnerOnly ? (
            <div className="form-grid">
              <label>
                Your submission
                <textarea value={drafts[item.id] ?? ""} onChange={(event) => setDrafts({ ...drafts, [item.id]: event.target.value })} />
              </label>
              <label>
                Text file
                <input
                  type="file"
                  accept=".txt,.md,.csv,text/plain"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (!file) return;
                    file.text().then((text) => setFiles({ ...files, [item.id]: { name: file.name, text: text.slice(0, 20000) } }));
                  }}
                />
              </label>
              <Btn
                variant="primary"
                disabled={(!(drafts[item.id] ?? "").trim() && !(files[item.id]?.text ?? "").trim()) || action.busy}
                onClick={() =>
                  action.run(async () => {
                    await send("POST", `/api/v1/assignments/${item.id}/submissions`, {
                      body: drafts[item.id] ?? "",
                      attachment_name: files[item.id]?.name ?? "",
                      attachment_text: files[item.id]?.text ?? "",
                    });
                    list.reload();
                    return item.submission ? "Submission updated." : "Submission received.";
                  })
                }
              >
                {item.submission ? "Update submission" : "Submit"}
              </Btn>
            </div>
          ) : null}
          {!learnerOnly && open === item.id ? (
            <div>
              {submissions.loading ? <Loading what="submissions" /> : null}
              {submissions.error ? <ErrorBox message={submissions.error} onRetry={submissions.reload} /> : null}
              {!submissions.loading && !(submissions.data ?? []).length ? <p>No submissions yet.</p> : null}
              {(submissions.data ?? []).map((sub) => {
                const grade = grades[sub.id] ?? { score: sub.score?.toString() ?? "", feedback: sub.feedback };
                return (
                  <div className="audit-row" key={sub.id}>
                    <span>
                      <strong>{sub.student_name}</strong>
                      <small>{sub.body}{sub.attachment_name ? ` · File ${sub.attachment_name}` : ""}{sub.submitted_at ? ` · ${new Date(sub.submitted_at).toLocaleString()}` : ""}</small>
                    </span>
                    <input
                      aria-label="Score"
                      type="number"
                      min={0}
                      max={100}
                      value={grade.score}
                      onChange={(event) => setGrades({ ...grades, [sub.id]: { ...grade, score: event.target.value } })}
                    />
                    <input
                      aria-label="Feedback"
                      placeholder="Feedback"
                      value={grade.feedback}
                      onChange={(event) => setGrades({ ...grades, [sub.id]: { ...grade, feedback: event.target.value } })}
                    />
                    <Btn
                      disabled={grade.score === "" || action.busy}
                      onClick={() =>
                        action.run(async () => {
                          await send("POST", `/api/v1/submissions/${sub.id}/grade`, { score: Number(grade.score), feedback: grade.feedback });
                          submissions.reload();
                          return `Graded ${sub.student_name}.`;
                        })
                      }
                    >
                      {sub.status === "graded" ? "Update" : "Grade"}
                    </Btn>
                  </div>
                );
              })}
            </div>
          ) : null}
        </section>
      ))}
    </div>
  );
}
