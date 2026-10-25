import { useState } from "react";
import { Badge, Btn, Empty, ErrorBox, Loading, useApi, useCoursePicker } from "./shared";
import { apiFetch } from "../api/client";

type ClassRow = {
  id: string;
  title: string;
  course_title: string;
  host_name: string;
  starts_at: string;
  duration_minutes: number;
  timezone: string;
};
type StudyRow = { id: string; title: string; starts_at: string; timezone: string };

function zoneName() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

function localInput(iso?: string) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function ScheduledClassList({ navigate }: { navigate: (module: string, sub?: string, detail?: string) => void }) {
  const classes = useApi<ClassRow[]>("/api/v1/classes");
  if (classes.loading) return <Loading what="scheduled classes" />;
  if (classes.error) return <ErrorBox message={classes.error} onRetry={classes.reload} />;
  if (!(classes.data ?? []).length) return <Empty title="No classes scheduled" hint="Instructor-led classes appear here after a teacher schedules one." />;
  return (
    <>
      {(classes.data ?? []).map((item, index) => (
        <button key={item.id} onClick={() => navigate("Virtual Classroom", "Live Classes", item.title)}>
          <span><strong>{item.title}</strong><small>{item.course_title} · {item.host_name}</small></span>
          <Badge tone={index === 0 ? "success" : "default"}>{new Date(item.starts_at).toLocaleString()} · {item.duration_minutes} min</Badge>
        </button>
      ))}
    </>
  );
}

export function ClassScheduler() {
  const { courseId, picker } = useCoursePicker();
  const classes = useApi<ClassRow[]>("/api/v1/classes");
  const [title, setTitle] = useState("");
  const [when, setWhen] = useState("");
  const [duration, setDuration] = useState("45");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (title.trim().length < 3 || !when || !courseId) {
      setNote("Enter a class title, course, and start time.");
      return;
    }
    setBusy(true);
    setNote("");
    try {
      await apiFetch("/api/v1/classes", {
        method: "POST",
        body: JSON.stringify({
          course_id: courseId,
          title: title.trim(),
          starts_at: new Date(when).toISOString(),
          duration_minutes: Number(duration),
          timezone: zoneName(),
        }),
      });
      setTitle("");
      setWhen("");
      setNote("Class scheduled.");
      classes.reload();
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Could not schedule the class");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    setNote("");
    try {
      await apiFetch(`/api/v1/classes/${id}`, { method: "DELETE" });
      classes.reload();
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Could not remove the class");
    }
  };

  return (
    <section className="card classroom-form">
      <div className="section-head"><div><span className="eyebrow">CLASS SETUP</span><h2>Schedule a live learning session</h2></div></div>
      <div className="form-grid">
        <label>Class title<input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Problem-solving workshop" /></label>
        {picker}
        <label>Start date and time<input type="datetime-local" value={when} onChange={(event) => setWhen(event.target.value)} /></label>
        <label>Duration
          <select value={duration} onChange={(event) => setDuration(event.target.value)}>
            <option value="45">45 minutes</option>
            <option value="60">60 minutes</option>
            <option value="90">90 minutes</option>
          </select>
        </label>
      </div>
      <p>Timezone {zoneName()}. Students in the course can see this class. They cannot create one.</p>
      <div className="panel-actions"><Btn onClick={save} disabled={busy}>{busy ? "Saving" : "Schedule class"}</Btn></div>
      {note ? <p>{note}</p> : null}
      {classes.loading ? <Loading what="classes" /> : null}
      {(classes.data ?? []).map((item) => (
        <div className="scope-row" key={item.id}>
          <span><strong>{item.title}</strong><small>{item.course_title} · {new Date(item.starts_at).toLocaleString()} · {item.timezone}</small></span>
          <Btn onClick={() => remove(item.id)}>Remove</Btn>
        </div>
      ))}
    </section>
  );
}

export function StudySessionBoard() {
  const sessions = useApi<StudyRow[]>("/api/v1/study-sessions");
  const [title, setTitle] = useState("");
  const [when, setWhen] = useState("");
  const [editing, setEditing] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (title.trim().length < 3 || !when) {
      setNote("Enter a session title and a date and time.");
      return;
    }
    const parsed = new Date(when);
    if (Number.isNaN(parsed.getTime())) {
      setNote("Enter a valid date and time.");
      return;
    }
    setBusy(true);
    setNote("");
    const body = JSON.stringify({ title: title.trim(), starts_at: parsed.toISOString(), timezone: zoneName() });
    try {
      if (editing) await apiFetch(`/api/v1/study-sessions/${editing}`, { method: "PATCH", body });
      else await apiFetch("/api/v1/study-sessions", { method: "POST", body });
      setTitle("");
      setWhen("");
      setEditing("");
      setNote("Study session saved to your account.");
      sessions.reload();
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Could not save the study session");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    setNote("");
    try {
      await apiFetch(`/api/v1/study-sessions/${id}`, { method: "DELETE" });
      if (editing === id) {
        setEditing("");
        setTitle("");
        setWhen("");
      }
      sessions.reload();
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Could not delete the study session");
    }
  };

  return (
    <div className="page-stack">
      <section className="title-row"><div><Badge tone="ai">PERSONAL STUDY</Badge><h1>Schedule Study/Revision Session</h1><p>This is your own revision time. It does not create an instructor-led class.</p></div></section>
      <section className="card classroom-form">
        <div className="section-head"><div><span className="eyebrow">STUDY SESSION</span><h2>{editing ? "Update your revision block" : "Plan a personal revision block"}</h2></div></div>
        <div className="form-grid">
          <label>Session focus<input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Review today's lesson" /></label>
          <label>When<input type="datetime-local" value={when} onChange={(event) => setWhen(event.target.value)} /></label>
        </div>
        <p>Saved in timezone {zoneName()} for your account only.</p>
        <div className="panel-actions"><Btn onClick={save} disabled={busy}>{busy ? "Saving" : editing ? "Update study session" : "Save study session"}</Btn></div>
        {note ? <p>{note}</p> : null}
        {sessions.loading ? <Loading what="study sessions" /> : null}
        {sessions.error ? <ErrorBox message={sessions.error} onRetry={sessions.reload} /> : null}
        {(sessions.data ?? []).map((item) => (
          <div className="scope-row" key={item.id}>
            <span><strong>{item.title}</strong><small>{new Date(item.starts_at).toLocaleString()} · {item.timezone}</small></span>
            <span>
              <Btn onClick={() => { setEditing(item.id); setTitle(item.title); setWhen(localInput(item.starts_at)); }}>Edit</Btn>
              <Btn onClick={() => remove(item.id)}>Delete</Btn>
            </span>
          </div>
        ))}
        {!(sessions.data ?? []).length && !sessions.loading ? <p>No study sessions yet.</p> : null}
      </section>
    </div>
  );
}
