import { useState } from "react";
import { Badge, Btn, Empty, ErrorBox, Loading, Notice, Title, send, useAction, useApi, type Nav } from "./shared";

type TeachingNote = {
  id: string;
  kind: string;
  title: string;
  body: string;
  status: string;
  author_name: string;
  created_at: string;
};

const TOOLS: Record<string, { kind: string; copy: string; placeholder: string }> = {
  "Lesson Planner": {
    kind: "lesson_plan",
    copy: "Save a lesson plan for this institution. The list shows records that were stored.",
    placeholder: "Objective, activities, and materials",
  },
  "Quiz Generator": {
    kind: "quiz",
    copy: "Save a quiz draft. Questions in the Question Bank stay on Assessments.",
    placeholder: "Questions, answers, and the course they belong to",
  },
  "Rubric Generator": {
    kind: "rubric",
    copy: "Save a rubric the faculty can reuse when scoring work.",
    placeholder: "Criteria and how each level is scored",
  },
  "Teaching Insights": {
    kind: "insight",
    copy: "Save an observation about a class. This does not invent learner scores.",
    placeholder: "What you observed and what should happen next",
  },
  "Student Support": {
    kind: "support",
    copy: "Save a support note for follow-up. It stays inside this institution.",
    placeholder: "Who needs support and the next step",
  },
};

const SUBS = ["Lesson Planner", "Content Generator", "Quiz Generator", "Rubric Generator", "Teaching Insights", "Student Support", "Class Analytics"];

export default function TeachingDesk({ sub, navigate }: { sub: string; navigate: Nav }) {
  const tool = TOOLS[sub];
  const notes = useApi<TeachingNote[]>(tool ? `/api/v1/teaching-notes?kind=${tool.kind}` : null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const action = useAction();
  const rows = notes.data ?? [];

  return (
    <div className="page-stack">
      <Title tag="TEACHING COPILOT · SAVED RECORDS" title={sub} copy={tool?.copy ?? "This tool does not have a saved record type."} />
      <div className="submodule-strip">
        {SUBS.map((item) => (
          <button className={item === sub ? "active" : ""} key={item} onClick={() => navigate("Teaching Copilot", item)}>
            {item}
          </button>
        ))}
      </div>
      {notes.loading ? <Loading what="saved notes" /> : null}
      {notes.error ? <ErrorBox message={notes.error} onRetry={notes.reload} /> : null}
      {tool ? (
        <section className="card form-grid">
          <label>
            Title
            <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder={`Title for this ${sub.toLowerCase()}`} />
          </label>
          <label>
            Record
            <textarea value={body} onChange={(event) => setBody(event.target.value)} placeholder={tool.placeholder} rows={5} />
          </label>
          <Btn
            variant="primary"
            disabled={action.busy || title.trim().length < 2 || body.trim().length < 1}
            onClick={() =>
              action.run(async () => {
                await send("POST", "/api/v1/teaching-notes", { kind: tool.kind, title: title.trim(), body: body.trim() });
                setTitle("");
                setBody("");
                notes.reload();
                return "Saved to this institution";
              })
            }
          >
            {action.busy ? "Saving..." : "Save"}
          </Btn>
        </section>
      ) : null}
      <Notice text={action.ok} tone="success" />
      <Notice text={action.fail} tone="danger" />
      {!notes.loading && !notes.error && rows.length === 0 ? (
        <Empty title="No saved records" hint="Create one with the form above. Sample rows are not shown here." />
      ) : null}
      {rows.length > 0 ? (
        <section className="card">
          <div className="section-head">
            <div>
              <span className="eyebrow">{rows.length} SAVED</span>
              <h2>Current records</h2>
            </div>
          </div>
          <div className="simple-table">
            <div className="simple-row head">
              <span>Name</span>
              <span>Status</span>
              <span>Details</span>
              <span />
            </div>
            {rows.map((row) => (
              <div className="simple-row" key={row.id}>
                <span>
                  <strong>{row.title}</strong>
                </span>
                <span>
                  <Badge tone="success">{row.status}</Badge>
                </span>
                <span>
                  {row.author_name} · {row.body.slice(0, 120)}
                </span>
                <span />
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
