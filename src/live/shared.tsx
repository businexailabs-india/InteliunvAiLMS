import { useEffect, useState, type ReactNode } from "react";
import { apiFetch, loadStoredSession } from "../api/client";

export type Nav = (module: string, sub?: string, detail?: string) => void;
export type CourseLite = { id: string; title: string; code?: string };

/** GET helper with loading / error state. Pass null to skip the request. */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(Boolean(path));
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!path) {
      setData(null);
      setLoading(false);
      return;
    }
    let alive = true;
    setLoading(true);
    setError("");
    apiFetch<T>(path)
      .then((value) => {
        if (alive) {
          setData(value);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (alive) {
          setError(err instanceof Error ? err.message : "Request failed");
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [path, tick]);
  return { data, error, loading, reload: () => setTick((value) => value + 1) };
}

export function send<T>(method: "POST" | "PATCH" | "PUT" | "DELETE", path: string, body?: unknown): Promise<T> {
  return apiFetch<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });
}

export function sessionRoles(): string[] {
  return loadStoredSession()?.roles ?? [];
}

export function hasRole(...codes: string[]): boolean {
  const roles = sessionRoles();
  return codes.some((code) => roles.includes(code));
}

export const COORDINATOR_CODES = ["coordinator", "principal_academic_director", "institution_admin", "platform_super_admin"];

export function Badge({ children, tone = "default" }: { children: ReactNode; tone?: "default" | "success" | "warning" | "danger" | "ai" }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function Btn({
  children,
  onClick,
  variant = "secondary",
  disabled = false,
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "secondary" | "danger";
  disabled?: boolean;
  className?: string;
}) {
  return (
    <button className={`btn btn-${variant} ${className}`} onClick={onClick} disabled={disabled} style={disabled ? { opacity: 0.55, cursor: "not-allowed" } : undefined}>
      <span>{children}</span>
    </button>
  );
}

export function Metric({ label, value, note }: { label: string; value: string | number; note?: string }) {
  return (
    <div className="kpi card">
      <div className="kpi-content">
        <span className="eyebrow">{label}</span>
        <strong>{value}</strong>
        <span className="muted">{note ?? "Live data"}</span>
      </div>
    </div>
  );
}

export function Title({ tag, title, copy, actions }: { tag: string; title: string; copy: string; actions?: ReactNode }) {
  return (
    <section className="title-row">
      <div>
        <Badge tone="ai">{tag}</Badge>
        <h1>{title}</h1>
        <p>{copy}</p>
      </div>
      {actions ? <div className="row-actions">{actions}</div> : null}
    </section>
  );
}

export function Loading({ what = "data" }: { what?: string }) {
  return (
    <div className="card" role="status" aria-live="polite">
      <span className="eyebrow">LOADING</span>
      <p>Loading {what} from the API...</p>
    </div>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="privacy-banner" role="alert">
      <div>
        <strong>Could not load this data</strong>
        <p>{message}</p>
      </div>
      {onRetry ? <Btn onClick={onRetry}>Retry</Btn> : null}
    </div>
  );
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="card">
      <span className="eyebrow">NOTHING HERE YET</span>
      <h2>{title}</h2>
      {hint ? <p>{hint}</p> : null}
    </div>
  );
}

export function Notice({ text, tone }: { text: string; tone: "success" | "danger" }) {
  if (!text) return null;
  return (
    <div className={tone === "success" ? "publish-success" : "privacy-banner"} role={tone === "danger" ? "alert" : "status"}>
      <div>
        <strong>{tone === "success" ? "Done" : "Action failed"}</strong>
        <p>{text}</p>
      </div>
    </div>
  );
}

/** Tracks the outcome of a mutation so screens can show success / error consistently. */
export function useAction() {
  const [ok, setOk] = useState("");
  const [fail, setFail] = useState("");
  const [busy, setBusy] = useState(false);
  async function run(work: () => Promise<string | void>) {
    setBusy(true);
    setOk("");
    setFail("");
    try {
      const message = await work();
      setOk(message || "Saved");
    } catch (err) {
      setFail(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }
  return { ok, fail, busy, run };
}

/** Course selector backed by /courses; first course is selected by default. */
export function useCoursePicker() {
  const courses = useApi<CourseLite[]>("/api/v1/courses");
  const [courseId, setCourseId] = useState("");
  useEffect(() => {
    if (!courseId && courses.data?.length) setCourseId(courses.data[0].id);
  }, [courses.data, courseId]);
  const picker = (
    <label>
      Course
      <select value={courseId} onChange={(event) => setCourseId(event.target.value)}>
        {(courses.data ?? []).map((course) => (
          <option key={course.id} value={course.id}>
            {course.code ? `${course.code} · ` : ""}
            {course.title}
          </option>
        ))}
      </select>
    </label>
  );
  return { courseId, picker, courses };
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
