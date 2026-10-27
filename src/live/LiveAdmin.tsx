import { useEffect, useMemo, useState } from "react";
import type { Roster } from "./LiveAcademics";
import {
  Badge,
  Btn,
  Empty,
  ErrorBox,
  Loading,
  Metric,
  Notice,
  Title,
  send,
  useAction,
  useApi,
  useCoursePicker,
  type CourseLite,
} from "./shared";

type AssessmentRow = { id: string; title: string; course_id: string; proctored: boolean };
type ProctorSession = { id: string; student_id: string; decision: string; synthetic: boolean; identity_check: string };
type ProctorEvent = { id: string; event_type: string; note: string; synthetic: boolean };

const DECISIONS: [string, string][] = [
  ["no_concern", "No concern"],
  ["needs_follow_up", "Needs follow-up"],
  ["escalated_to_academic_integrity", "Escalate to academic integrity process"],
];

/** Human review of simulated integrity signals. Nothing here can disqualify a learner automatically. */
export function LiveProctoring() {
  const assessments = useApi<AssessmentRow[]>("/api/v1/assessments");
  const [assessmentId, setAssessmentId] = useState("");
  const [selected, setSelected] = useState("");
  const [decision, setDecision] = useState(DECISIONS[0][0]);
  const [notes, setNotes] = useState("");
  const action = useAction();

  useEffect(() => {
    if (!assessmentId && assessments.data?.length) setAssessmentId(assessments.data[0].id);
  }, [assessments.data, assessmentId]);

  const courseId = assessments.data?.find((a) => a.id === assessmentId)?.course_id;
  const roster = useApi<Roster>(courseId ? `/api/v1/roster?course_id=${courseId}` : null);
  const sessions = useApi<ProctorSession[]>(assessmentId ? `/api/v1/proctoring?assessment_id=${assessmentId}` : null);
  const events = useApi<ProctorEvent[]>(selected ? `/api/v1/proctoring/${selected}/events` : null);
  const names = useMemo(() => new Map((roster.data?.learners ?? []).map((l) => [l.student_id, l.name])), [roster.data]);
  const rows = sessions.data ?? [];

  return (
    <div className="page-stack">
      <Title
        tag="PROCTORING · HUMAN REVIEW"
        title="Integrity Review"
        copy="Signals are simulated for the demo and support human review. They never establish misconduct and never disqualify a learner automatically."
      />
      <div className="card form-grid">
        <label>
          Assessment
          <select
            value={assessmentId}
            onChange={(event) => {
              setAssessmentId(event.target.value);
              setSelected("");
            }}
          >
            {(assessments.data ?? []).map((a) => (
              <option key={a.id} value={a.id}>
                {a.title}
                {a.proctored ? " (proctored)" : ""}
              </option>
            ))}
          </select>
        </label>
      </div>
      <Notice text={action.ok} tone="success" />
      <Notice text={action.fail} tone="danger" />
      <div className="kpi-grid compact">
        <Metric label="SESSIONS" value={rows.length} />
        <Metric label="AWAITING REVIEW" value={rows.filter((r) => r.decision === "pending" || r.decision === "pending_review").length} />
        <Metric label="FOLLOW-UP / ESCALATED" value={rows.filter((r) => r.decision === "needs_follow_up" || r.decision === "escalated_to_academic_integrity").length} />
      </div>
      {assessments.loading || sessions.loading ? <Loading what="sessions" /> : null}
      {assessments.error ? <ErrorBox message={assessments.error} onRetry={assessments.reload} /> : null}
      {sessions.error ? <ErrorBox message={sessions.error} onRetry={sessions.reload} /> : null}
      {!sessions.loading && assessmentId && !sessions.error && !rows.length ? (
        <Empty title="No proctoring sessions for this assessment" hint="Sessions appear when a learner starts a proctored attempt." />
      ) : null}
      {rows.length ? (
        <div className="content-grid">
          <section className="card span-2">
            {rows.map((row) => (
              <button className="simple-row" key={row.id} onClick={() => setSelected(row.id)}>
                <span>
                  <strong>{names.get(row.student_id) ?? row.student_id.slice(0, 8)}</strong>
                </span>
                <span>Identity: {row.identity_check}</span>
                <Badge tone={row.decision === "no_concern" ? "success" : row.decision === "pending" ? "default" : "warning"}>
                  {row.decision.replace(/_/g, " ").toUpperCase()}
                </Badge>
                {row.synthetic ? <Badge tone="ai">SYNTHETIC</Badge> : null}
              </button>
            ))}
          </section>
          <aside className="card">
            <span className="eyebrow">EVIDENCE TIMELINE</span>
            {!selected ? <p>Select a session to review its events.</p> : null}
            {events.loading ? <Loading what="events" /> : null}
            {events.error ? <ErrorBox message={events.error} onRetry={events.reload} /> : null}
            {(events.data ?? []).map((event) => (
              <div className="audit-row" key={event.id}>
                <span>
                  <strong>{event.event_type.replace(/_/g, " ")}</strong>
                  <small>{event.note}</small>
                </span>
              </div>
            ))}
            {selected ? (
              <div className="form-grid">
                <label>
                  Reviewer decision
                  <select value={decision} onChange={(event) => setDecision(event.target.value)}>
                    {DECISIONS.map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Review notes
                  <textarea value={notes} onChange={(event) => setNotes(event.target.value)} />
                </label>
                <Btn
                  variant="primary"
                  disabled={action.busy}
                  onClick={() =>
                    action.run(async () => {
                      await send("POST", `/api/v1/proctoring/${selected}/review`, { decision, notes });
                      sessions.reload();
                      setNotes("");
                      return "Review decision recorded in the audit log.";
                    })
                  }
                >
                  Record human decision
                </Btn>
              </div>
            ) : null}
          </aside>
        </div>
      ) : null}
    </div>
  );
}

type BankItem = { id: string; course_id: string | null; qtype: string; prompt: string; options: string[]; answer: string | null; points: number; difficulty: string; status: string };

/** Question bank with four-eyes approval and quiz generation from approved items. */
export function LiveQuestionBank() {
  const { courseId, picker } = useCoursePicker();
  const items = useApi<BankItem[]>(courseId ? `/api/v1/question-bank?course_id=${courseId}` : null);
  const [prompt, setPrompt] = useState("");
  const [options, setOptions] = useState(["", "", "", ""]);
  const [answer, setAnswer] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [quizTitle, setQuizTitle] = useState("");
  const action = useAction();
  const filled = options.map((o) => o.trim()).filter(Boolean);
  const canCreate = prompt.trim().length >= 3 && filled.length >= 2 && filled.includes(answer);
  const rows = items.data ?? [];

  return (
    <div className="page-stack">
      <Title
        tag="QUESTION BANK · LIVE"
        title="Question Bank & Quiz Builder"
        copy="Author questions, have a different reviewer approve them, then assemble a quiz. Only approved questions can be used."
      />
      <div className="card form-grid">{picker}</div>
      <Notice text={action.ok} tone="success" />
      <Notice text={action.fail} tone="danger" />
      <section className="card form-grid">
        <span className="eyebrow">NEW MULTIPLE-CHOICE QUESTION</span>
        <label>
          Prompt
          <input value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Which join returns all rows from the left table?" />
        </label>
        {options.map((value, index) => (
          <label key={index}>
            Option {String.fromCharCode(65 + index)}
            <input
              value={value}
              onChange={(event) => setOptions(options.map((o, i) => (i === index ? event.target.value : o)))}
            />
          </label>
        ))}
        <label>
          Correct answer
          <select value={answer} onChange={(event) => setAnswer(event.target.value)}>
            <option value="">Select the correct option</option>
            {filled.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <Btn
          variant="primary"
          disabled={!canCreate || action.busy}
          onClick={() =>
            action.run(async () => {
              await send("POST", "/api/v1/question-bank", { course_id: courseId, prompt: prompt.trim(), options: filled, answer });
              setPrompt("");
              setOptions(["", "", "", ""]);
              setAnswer("");
              items.reload();
              return "Draft saved. A different reviewer must approve it.";
            })
          }
        >
          Save draft question
        </Btn>
      </section>
      {items.loading ? <Loading what="questions" /> : null}
      {items.error ? <ErrorBox message={items.error} onRetry={items.reload} /> : null}
      {!items.loading && !items.error && !rows.length ? <Empty title="No questions for this course yet" /> : null}
      {rows.length ? (
        <section className="card">
          {rows.map((row) => (
            <div className="audit-row" key={row.id}>
              <label>
                <input
                  type="checkbox"
                  disabled={row.status !== "approved"}
                  checked={picked.includes(row.id)}
                  onChange={(event) => setPicked(event.target.checked ? [...picked, row.id] : picked.filter((id) => id !== row.id))}
                  aria-label={`Select ${row.prompt}`}
                />
              </label>
              <span>
                <strong>{row.prompt}</strong>
                <small>
                  {row.options.join(" · ")} — answer: {row.answer}
                </small>
              </span>
              <Badge tone={row.status === "approved" ? "success" : "warning"}>{row.status.toUpperCase()}</Badge>
              {row.status !== "approved" ? (
                <Btn
                  disabled={action.busy}
                  onClick={() =>
                    action.run(async () => {
                      await send("POST", `/api/v1/question-bank/${row.id}/approve`);
                      items.reload();
                      return "Question approved.";
                    })
                  }
                >
                  Approve
                </Btn>
              ) : (
                <span />
              )}
            </div>
          ))}
          <div className="form-grid">
            <label>
              Quiz title
              <input value={quizTitle} onChange={(event) => setQuizTitle(event.target.value)} />
            </label>
            <Btn
              variant="primary"
              disabled={!picked.length || quizTitle.trim().length < 2 || action.busy}
              onClick={() =>
                action.run(async () => {
                  await send("POST", "/api/v1/assessments/from-bank", { course_id: courseId, title: quizTitle.trim(), item_ids: picked });
                  setPicked([]);
                  setQuizTitle("");
                  return `Quiz created from ${picked.length} approved questions.`;
                })
              }
            >
              Build quiz from selected
            </Btn>
          </div>
        </section>
      ) : null}
    </div>
  );
}

type BillingData = { plan: { code: string; name: string } | null; status: string; invoices: { id: string; amount: number; currency: string; status: string; synthetic: boolean }[] };
type UsageData = { quota: number; used: number; events: { feature: string; provider: string; tokens_in: number; tokens_out: number }[] };

/** Subscription, invoices and AI token quota for the tenant. */
export function LiveBilling() {
  const billing = useApi<BillingData>("/api/v1/billing");
  const subscription = useApi<{ status: string; renews_at?: string | null; display?: string; currency?: string; plan?: { name: string } | null }>("/api/v1/billing/subscription");
  const entitlements = useApi<{ features: Record<string, boolean>; plan?: string }>("/api/v1/billing/entitlements");
  const usage = useApi<UsageData>("/api/v1/ai/usage");
  const [quota, setQuota] = useState("");
  const action = useAction();
  const pct = usage.data && usage.data.quota ? Math.min(100, Math.round((100 * usage.data.used) / usage.data.quota)) : 0;

  return (
    <div className="page-stack">
      <Title
        tag="BILLING · LIVE"
        title="Subscription & AI Usage"
        copy="Plan, invoices, and the tenant AI quota. A paid plan becomes active only after the server verifies the payment."
      />
      <Notice text={action.ok} tone="success" />
      <Notice text={action.fail} tone="danger" />
      {billing.loading || usage.loading ? <Loading what="billing" /> : null}
      {billing.error ? <ErrorBox message={billing.error} onRetry={billing.reload} /> : null}
      {billing.data ? (
        <div className="kpi-grid compact">
          <Metric label="PLAN" value={billing.data.plan?.name ?? "None"} note={`Status: ${billing.data.status}`} />
          <Metric label="AI TOKENS USED" value={usage.data ? usage.data.used.toLocaleString() : "—"} note={usage.data ? `${pct}% of ${usage.data.quota.toLocaleString()}` : ""} />
          <Metric label="INVOICES" value={billing.data.invoices.length} />
        </div>
      ) : null}
      {subscription.data ? (
        <section className="card">
          <span className="eyebrow">SUBSCRIPTION</span>
          <p>
            {subscription.data.plan?.name ?? "No plan"} · {subscription.data.status}
            {subscription.data.display ? ` · ${subscription.data.display} ${subscription.data.currency ?? ""}` : ""}
            {subscription.data.renews_at ? ` · renews ${new Date(subscription.data.renews_at).toLocaleDateString()}` : ""}
          </p>
          {entitlements.data?.features ? (
            <p>{Object.entries(entitlements.data.features).filter(([, on]) => on).map(([name]) => name.replaceAll("_", " ")).join(", ") || "No extra features"}</p>
          ) : null}
          <Btn variant="secondary" disabled={action.busy} onClick={() => action.run(async () => { await send("POST", "/api/v1/billing/subscription/cancel", { at_period_end: true }); subscription.reload(); return "Cancellation is scheduled for the end of the period."; })}>Cancel at period end</Btn>
          <Btn variant="primary" disabled={action.busy} onClick={() => action.run(async () => { await send("POST", "/api/v1/billing/subscription/reactivate"); subscription.reload(); return "Subscription reactivated."; })}>Reactivate</Btn>
        </section>
      ) : null}
      {usage.data ? (
        <section className="card form-grid">
          <span className="eyebrow">MONTHLY AI TOKEN QUOTA</span>
          <label>
            New quota (tokens)
            <input type="number" min={0} value={quota} onChange={(event) => setQuota(event.target.value)} placeholder={String(usage.data.quota)} />
          </label>
          <Btn
            variant="primary"
            disabled={quota === "" || Number(quota) < 0 || action.busy}
            onClick={() =>
              action.run(async () => {
                await send("PATCH", "/api/v1/billing/ai-quota", { monthly_token_quota: Number(quota) });
                setQuota("");
                usage.reload();
                return "AI quota updated. Requests beyond the quota return HTTP 429.";
              })
            }
          >
            Update quota
          </Btn>
        </section>
      ) : null}
      {billing.data && !billing.data.invoices.length ? <Empty title="No invoices yet" /> : null}
      {billing.data?.invoices.length ? (
        <section className="card">
          <span className="eyebrow">INVOICES</span>
          {billing.data.invoices.map((invoice) => (
            <div className="audit-row" key={invoice.id}>
              <span>
                <strong>
                  {invoice.currency} {invoice.amount}
                </strong>
                <small>{invoice.id.slice(0, 8)}</small>
              </span>
              <Badge tone={invoice.status === "paid" ? "success" : "warning"}>{invoice.status.toUpperCase()}</Badge>
              {invoice.synthetic ? <Badge tone="ai">SYNTHETIC</Badge> : null}
            </div>
          ))}
        </section>
      ) : null}
      {usage.data?.events.length ? (
        <section className="card">
          <span className="eyebrow">RECENT AI REQUESTS</span>
          {usage.data.events.map((event, index) => (
            <div className="audit-row" key={index}>
              <span>
                <strong>{event.feature}</strong>
                <small>Provider: {event.provider}</small>
              </span>
              <span>
                {event.tokens_in + event.tokens_out} tokens
              </span>
            </div>
          ))}
        </section>
      ) : null}
    </div>
  );
}

type CohortRow = { cohort_id: string; name: string; course_id: string | null; members: number; avg_progress_pct: number; attempts_taken: number; members_passed: number; completion_rate_pct: number; pass_mark: number };
type Person = { id: string; display_name: string; email: string | null };

/** Corporate cohorts: create, add members from the directory, and track completion. */
export function LiveCompletionReport() {
  const report = useApi<{ cohorts: CohortRow[] }>("/api/v1/reports/completion");
  const courses = useApi<CourseLite[]>("/api/v1/courses");
  const [name, setName] = useState("");
  const [courseId, setCourseId] = useState("");
  const [active, setActive] = useState("");
  const [query, setQuery] = useState("");
  const directory = useApi<Person[]>(active ? `/api/v1/directory?q=${encodeURIComponent(query)}` : null);
  const action = useAction();
  const cohorts = report.data?.cohorts ?? [];
  const course = courseId || courses.data?.[0]?.id || "";

  return (
    <div className="page-stack">
      <Title
        tag="BATCHES"
        title="Batches"
        copy="A batch is a cohort tied to one course. Create it here, then add students from the directory. Completion counts members who scored 60% or higher."
      />
      <Notice text={action.ok} tone="success" />
      <Notice text={action.fail} tone="danger" />
      <section className="card form-grid">
        <span className="eyebrow">NEW COHORT</span>
        <label>
          Cohort name
          <input value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <label>
          Course
          <select value={course} onChange={(event) => setCourseId(event.target.value)}>
            {(courses.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </select>
        </label>
        <Btn
          variant="primary"
          disabled={name.trim().length < 2 || !course || action.busy}
          onClick={() =>
            action.run(async () => {
              await send("POST", "/api/v1/cohorts", { name: name.trim(), course_id: course });
              setName("");
              report.reload();
              return "Cohort created.";
            })
          }
        >
          Create cohort
        </Btn>
      </section>
      {report.loading ? <Loading what="completion report" /> : null}
      {report.error ? <ErrorBox message={report.error} onRetry={report.reload} /> : null}
      {!report.loading && !report.error && !cohorts.length ? <Empty title="No cohorts yet" hint="Create a cohort, then add employees to it." /> : null}
      {cohorts.map((cohort) => (
        <section className="card" key={cohort.cohort_id}>
          <div className="section-head">
            <div>
              <span className="eyebrow">COHORT</span>
              <h2>{cohort.name}</h2>
            </div>
            <Badge tone={cohort.completion_rate_pct >= 80 ? "success" : "warning"}>{cohort.completion_rate_pct}% COMPLETE</Badge>
          </div>
          <div className="kpi-grid compact">
            <Metric label="MEMBERS" value={cohort.members} />
            <Metric label="AVG PROGRESS" value={`${cohort.avg_progress_pct}%`} />
            <Metric label="ATTEMPTS" value={cohort.attempts_taken} />
            <Metric label="PASSED" value={`${cohort.members_passed}/${cohort.members}`} />
          </div>
          <Btn onClick={() => setActive(active === cohort.cohort_id ? "" : cohort.cohort_id)}>{active === cohort.cohort_id ? "Close" : "Add members"}</Btn>
          {active === cohort.cohort_id ? (
            <div className="form-grid">
              <label>
                Search directory
                <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name or email" />
              </label>
              {directory.loading ? <Loading what="directory" /> : null}
              {directory.error ? <ErrorBox message={directory.error} /> : null}
              {(directory.data ?? []).map((person) => (
                <div className="audit-row" key={person.id}>
                  <span>
                    <strong>{person.display_name}</strong>
                    <small>{person.email}</small>
                  </span>
                  <Btn
                    disabled={action.busy}
                    onClick={() =>
                      action.run(async () => {
                        const done = await send<{ added: number; newly_enrolled: number }>("POST", `/api/v1/cohorts/${cohort.cohort_id}/members`, { user_ids: [person.id] });
                        report.reload();
                        return done.added ? `Added ${person.display_name} (${done.newly_enrolled} new enrollment).` : `${person.display_name} is already a member.`;
                      })
                    }
                  >
                    Add
                  </Btn>
                </div>
              ))}
            </div>
          ) : null}
        </section>
      ))}
    </div>
  );
}

type Attendance = { id: string; course_id: string; sessions_total: number; sessions_present: number; status: string };
type Result = { id: string; assessment_id: string; score: number | null; status: string; published: boolean };
type Learner = { id: string; display_name: string };

/** Learner or linked-parent view of published results and attendance. */
export function LivePersonalRecord({ module, parent }: { module: "Attendance" | "Gradebook"; parent: boolean }) {
  const learners = useApi<Learner[]>(parent ? "/api/v1/parents/learners" : null);
  const [studentId, setStudentId] = useState("");
  useEffect(() => {
    if (parent && !studentId && learners.data?.length) setStudentId(learners.data[0].id);
  }, [parent, learners.data, studentId]);
  const suffix = parent && studentId ? `?student_id=${studentId}` : "";
  const ready = !parent || Boolean(studentId);
  const attendance = useApi<Attendance[]>(module === "Attendance" && ready ? `/api/v1/attendance${suffix}` : null);
  const results = useApi<Result[]>(module === "Gradebook" && ready ? `/api/v1/results${suffix}` : null);
  const courses = useApi<CourseLite[]>("/api/v1/courses");
  const assessments = useApi<AssessmentRow[]>("/api/v1/assessments");
  const courseName = new Map((courses.data ?? []).map((c) => [c.id, c.title]));
  const assessmentName = new Map((assessments.data ?? []).map((a) => [a.id, a.title]));
  const scored = (results.data ?? []).filter((r) => r.score !== null);
  const average = scored.length ? scored.reduce((sum, r) => sum + (r.score ?? 0), 0) / scored.length : null;
  const attRows = attendance.data ?? [];
  const totalSessions = attRows.reduce((sum, r) => sum + r.sessions_total, 0);
  const present = attRows.reduce((sum, r) => sum + r.sessions_present, 0);
  const action = useAction();

  return (
    <div className="page-stack">
      <Title
        tag="PRIVATE LEARNER RECORD"
        title={module === "Attendance" ? "Attendance" : "Results"}
        copy={module === "Gradebook" ? "Published scores only. A coordinator publishes them from Assessments, then Results." : parent ? "Records for your linked learners only. Results appear after a coordinator publishes them." : "Your own records. You can confirm attendance only for yourself."}
        actions={
          module === "Attendance" && !parent ? (
            <Btn
              variant="primary"
              disabled={action.busy || !(courses.data ?? []).length}
              onClick={() =>
                action.run(async () => {
                  const courseId = (courses.data ?? [])[0]?.id;
                  if (!courseId) return "Enroll in a course before confirming attendance.";
                  await send("POST", "/api/v1/attendance/check-in", { course_id: courseId, status: "present" });
                  attendance.reload();
                  return "Your attendance was recorded.";
                })
              }
            >
              {action.busy ? "Saving..." : "Confirm my attendance"}
            </Btn>
          ) : null
        }
      />
      <Notice text={action.ok} tone="success" />
      <Notice text={action.fail} tone="danger" />
      {parent ? (
        <div className="card form-grid">
          <label>
            Linked learner
            <select value={studentId} onChange={(event) => setStudentId(event.target.value)}>
              {(learners.data ?? []).map((l) => (
                <option key={l.id} value={l.id}>
                  {l.display_name}
                </option>
              ))}
            </select>
          </label>
        </div>
      ) : null}
      {parent && !learners.loading && !(learners.data ?? []).length ? <Empty title="No linked learners" hint="Ask the institution to link your account to a learner." /> : null}
      {learners.error ? <ErrorBox message={learners.error} onRetry={learners.reload} /> : null}
      {attendance.loading || results.loading ? <Loading what="records" /> : null}
      {attendance.error ? <ErrorBox message={attendance.error} onRetry={attendance.reload} /> : null}
      {results.error ? <ErrorBox message={results.error} onRetry={results.reload} /> : null}
      {module === "Attendance" && attendance.data ? (
        <>
          <div className="kpi-grid compact">
            <Metric label="OVERALL" value={totalSessions ? `${Math.round((100 * present) / totalSessions)}%` : "No sessions"} />
            <Metric label="PRESENT" value={`${present}/${totalSessions}`} />
          </div>
          {!attRows.length ? <Empty title="No attendance recorded yet" /> : null}
          <section className="card">
            {attRows.map((row) => (
              <div className="scope-row record" key={row.id}>
                <span>
                  <strong>{courseName.get(row.course_id) ?? "Course"}</strong>
                  <small>
                    {row.sessions_present} of {row.sessions_total} sessions
                  </small>
                </span>
                <Badge tone={row.sessions_total && row.sessions_present / row.sessions_total >= 0.75 ? "success" : "warning"}>
                  {row.sessions_total ? Math.round((100 * row.sessions_present) / row.sessions_total) : 0}%
                </Badge>
              </div>
            ))}
          </section>
        </>
      ) : null}
      {module === "Gradebook" && results.data ? (
        <>
          <div className="kpi-grid compact">
            <Metric label="PUBLISHED RESULTS" value={results.data.length} />
            <Metric label="AVERAGE" value={average === null ? "No scores" : `${average.toFixed(1)}%`} />
          </div>
          {!results.data.length ? <Empty title="No published results yet" hint="Results show here once your coordinator approves the scorecard." /> : null}
          <section className="card">
            {results.data.map((row) => (
              <div className="scope-row record" key={row.id}>
                <span>
                  <strong>{assessmentName.get(row.assessment_id) ?? "Assessment"}</strong>
                  <small>{row.status}</small>
                </span>
                <Badge tone={(row.score ?? 0) >= 60 ? "success" : "warning"}>{row.score ?? "—"}%</Badge>
              </div>
            ))}
          </section>
        </>
      ) : null}
    </div>
  );
}
