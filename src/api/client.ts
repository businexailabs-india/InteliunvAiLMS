export type UiRole =
  | "Student"
  | "Teacher / Faculty"
  | "Training Coordinator"
  | "Parent / Guardian / HOD"
  | "Principal / L&D Lead"
  | "Administrator"

export type Session = {
  access_token: string
  user_id: string
  display_name: string
  email: string | null
  institution_id: string
  institution_name: string
  institution_slug: string
  roles: string[]
  permissions?: string[]
  auth_mode: string
  synthetic: boolean
}

export type CourseRecord = {
  id: string
  title: string
  level: string
  status: string
  description: string
  synthetic: boolean
  code?: string
  category?: string
  modules?: { id: string }[]
  progress_pct?: number
}

export type Course = CourseRecord

export type DashboardRecord = {
  role: string
  metrics: Record<string, unknown>
  courses: CourseRecord[]
  notifications: { id: string; title: string; body: string; read: boolean }[]
  schedule?: { title: string; course: string; when: string; today: boolean }[]
  alerts?: { title: string; detail: string; module: string; sub: string }[]
  activity?: { label: string; completions: number }[]
  overview?: { name: string; signal: string; status: string }[]
}

export type Dashboard = DashboardRecord

const TOKEN_KEY = "businex.session"

export function mapRole(roles: string[]): UiRole {
  const codes = new Set(roles)
  if (codes.has("student")) return "Student"
  if (codes.has("teacher") || codes.has("corporate_trainer") || codes.has("content_reviewer")) {
    return "Teacher / Faculty"
  }
  if (codes.has("coordinator")) return "Training Coordinator"
  if (codes.has("parent_guardian")) return "Parent / Guardian / HOD"
  if (codes.has("principal_academic_director") || codes.has("corporate_hr")) {
    return "Principal / L&D Lead"
  }
  return "Administrator"
}

export const mapBackendRole = mapRole

export function loadStoredSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(TOKEN_KEY)
    return raw ? (JSON.parse(raw) as Session) : null
  } catch {
    return null
  }
}

export function storeSession(session: Session | null): void {
  if (!session) {
    sessionStorage.removeItem(TOKEN_KEY)
    return
  }
  sessionStorage.setItem(TOKEN_KEY, JSON.stringify(session))
}

export function getStoredToken(): string | null {
  return loadStoredSession()?.access_token ?? null
}

export function clearToken(): void {
  storeSession(null)
}

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set("Content-Type", "application/json")
  if (token) headers.set("Authorization", `Bearer ${token}`)
  const response = await fetch(path, { ...init, headers })
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const body = (await response.json()) as { detail?: string }
      if (typeof body.detail === "string") detail = body.detail
    } catch {
      /* keep default */
    }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getStoredToken()
  if (!token) throw new Error("Not signed in")
  return request<T>(path, init, token)
}

export async function registerAccount(input: {
  email: string
  password: string
  first_name: string
  last_name: string
  role: string
  institution_name: string
  create_institution: boolean
}): Promise<Session> {
  const session = await request<Session>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify(input),
  })
  storeSession(session)
  return session
}

export async function demoLogin(email: string, password: string): Promise<Session> {
  const session = await request<Session>("/api/v1/auth/demo-login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  })
  storeSession(session)
  return session
}

export const api = {
  login: demoLogin,
  dashboard(token: string): Promise<DashboardRecord> {
    return request<DashboardRecord>("/api/v1/dashboard", { method: "GET" }, token)
  },
  courses(token: string): Promise<CourseRecord[]> {
    return request<CourseRecord[]>("/api/v1/courses", { method: "GET" }, token)
  },
  lessons(token: string, courseId: string): Promise<{ id: string; title: string }[]> {
    return request(`/api/v1/courses/${courseId}/lessons`, { method: "GET" }, token)
  },
  completeLesson(token: string, lessonId: string): Promise<{ completed: boolean }> {
    return request("/api/v1/progress", {
      method: "POST",
      body: JSON.stringify({ lesson_id: lessonId }),
    }, token)
  },
  assessments(token: string): Promise<{ id: string; title: string; proctored: boolean }[]> {
    return request("/api/v1/assessments", { method: "GET" }, token)
  },
  submitAttempt(
    token: string,
    assessmentId: string,
    answers: { question_id: string; value: string }[],
  ): Promise<{ score: number | null; status: string }> {
    return request(`/api/v1/assessments/${assessmentId}/attempts`, {
      method: "POST",
      body: JSON.stringify({ answers }),
    }, token)
  },
  studyBuddy(token: string, message: string): Promise<{ reply: string; mock: boolean; citations: { title: string }[] }> {
    return request("/api/v1/ai/study-buddy", {
      method: "POST",
      body: JSON.stringify({ message, feature: "study_buddy" }),
    }, token)
  },
  playGame(token: string, gameType: string): Promise<{ xp_awarded: number; total_xp: number }> {
    return request("/api/v1/gamification/play", {
      method: "POST",
      body: JSON.stringify({
        game_type: gameType,
        correct: 8,
        total: 10,
        elapsed_seconds: 16,
        source_event_id: crypto.randomUUID(),
      }),
    }, token)
  },
  gamification(token: string): Promise<{ total_xp: number; games: { id: string; name: string }[] }> {
    return request("/api/v1/gamification", { method: "GET" }, token)
  },
}
