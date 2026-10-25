# Integration status

Measured against the running Docker Compose stack. Only checks that were actually executed are
listed as passing. Everything synthetic is labelled synthetic; no real personal data is used.

## How to run it

```powershell
docker compose -f infra/containers/compose.yaml up -d      # postgres, redis, keycloak, api, worker, web
# API: http://localhost:8000 (docs at /docs)   Web: http://localhost:8443
# Demo logins (password Demo@2025): aarav.sharma (student), maya.chen (teacher), riya.nair (coordinator),
# priya.sharma (parent), david.wilson (principal), olivia.harris (institution admin) @inteluniven.edu
```

The API container applies migrations on start. Import the starter synthetic data (idempotent):

```powershell
docker exec containers-api-1 python -m app.import_seed --root /data/synthetic
```

## Tests

| Suite | Command | What it proves |
|---|---|---|
| Unit (47 tests) | `docker exec containers-api-1 python -m pytest tests --ignore=tests/test_live_stack.py --ignore=tests/test_rls.py` | grading, RBAC matrix, mock AI labelling, real-provider adapters (mock transport), synthetic-data hygiene |
| Row-level security (12) | `docker exec containers-api-1 python -m pytest tests/test_rls.py` | no tenant context sees nothing, each tenant sees only its rows, cross-tenant insert rejected by Postgres |
| Live stack (3) | `python -m pytest services/api/tests/test_live_stack.py` | runs all scenarios below and fails on any FAIL |
| Scenarios (112 checks) | `python scripts/verify_integration.py` | the 10 business scenarios plus RBAC, isolation, audit and negative cases |
| Web smoke (13) | `python scripts/smoke_web.py` | Vite compiles the live screens, `/api` proxies to FastAPI, RBAC holds through the proxy |
| Menu access rules (40) | `node scripts/check_access.mts` | which modules each role sees (`src/access.ts`), every live screen is reachable by its role, finance and support get narrower menus. Navigation only; the API remains the security boundary |
| Browser (29) | `cd e2e; npx playwright test` | each persona signs in, sidebar matches the access rules, every live screen opens with no API error, bad logins are refused, session survives reload |
| Frontend | `tsc --noEmit` and `vite build` inside the web container | typecheck and production build |

pytest is not baked into the API image. Install the dev extras (`pip install -e .[dev]`) or, as
done in this environment, make pytest importable with `PYTHONPATH`.

## Backend surface

| Router | Endpoints |
|---|---|
| `auth` | `POST /auth/demo-login`, `GET /auth/me` |
| `lms` | institutions/current, dashboard, courses, lessons, progress, enrollments, attendance (read), assessments, attempts, results, results/{id}/adjust, scorecards (+approve), assignments (create, submit), parents/learners, cohorts, notifications, profile |
| `training` | `POST/GET /question-bank`, `POST /question-bank/{id}/approve`, `POST /assessments/from-bank`, `POST /cohorts/{id}/members`, `GET /reports/completion` |
| `academics` | `GET /assignments`, `GET /assignments/{id}/submissions`, `POST /submissions/{id}/grade`, `POST /attendance/record`, `PATCH /attendance/{id}`, `GET /directory`, `GET /roster` |
| `engagement` | gamification (+play, rank, leaderboard), proctoring sessions/events/review, billing, `PATCH /billing/ai-quota` |
| `ai` | study-buddy, teacher-copilot, adaptive-learning, student-success, usage |

## Database

Alembic revisions `0001`-`0003`. Tenant-owned tables use forced RLS keyed on
`app.institution_id`. `0003` added `cohort_members` and `question_bank_items`. Attendance
corrections, score adjustments, proctoring reviews, scorecard approvals, question approvals and
quota changes all write `audit_logs`.

## Frontend screens connected to the API

Live screens are used when a real session exists; prototype mode keeps the original static
screens.

| Screen | Role | API |
|---|---|---|
| Login, Dashboard, Courses, Lesson (mark complete) | all | auth, dashboard, courses, lessons, progress |
| AI Study Buddy | student | `/ai/study-buddy` |
| Assessment Center | student | assessments, attempts |
| Quick Quest | student | gamification |
| Assignments | student, teacher, coordinator, admin | assignments, submissions, grade |
| Attendance | coordinator, staff | roster, attendance record/correct |
| Attendance and Gradebook (personal) | student, parent | attendance, results, parents/learners |
| Student & Batch Management, Gradebook | coordinator, staff | roster |
| Assessment results and scorecards | coordinator | assessments, results, adjust, scorecards |
| Proctoring review | all reviewers | proctoring, events, review |
| Quiz Builder / question bank | teacher, admin | question-bank, approve, from-bank |
| Administration - Billing | admin | billing, ai/usage, ai-quota |
| Analytics (cohort completion) | principal / L&D, admin | reports/completion, cohorts, directory, members |

## Known limitations

- Authentication in the UI uses demo login. Keycloak is running and the API can verify its
  tokens (`BUSINEX_AUTH_MODE=oidc`), but the UI has no OIDC redirect flow yet.
- AI defaults to the mock provider and every mock response is labelled. The OpenAI, Azure OpenAI
  and Gemini adapters are implemented and unit-tested against a mock transport only; they have
  not been exercised with real keys.
- Retrieval is a token-overlap stand-in over `source_chunks`. There is no pgvector (the Postgres
  image has no extension) and no embeddings.
- No MinIO / object storage, no file upload and no Celery tasks beyond the worker scaffold.
- No badges, streaks or daily challenges (XP, rank and leaderboard exist).
- Proctoring events are synthetic. Reviewers choose from no concern / follow-up / escalate; the
  system never disqualifies automatically.
- Many prototype screens remain static: Virtual Classroom, Digital Library, Collaboration,
  Communication, Credentials, Learning Intelligence, Integrations, Calendar and others.
- Only the demo personas exist in every tenant (by design, so any tenant is explorable). The
  synthetic JSON users belong to exactly one tenant, and some are deliberately inactive.
- The API image was not rebuilt in this environment (PyPI timeouts); changed files were copied
  into the running containers. A clean `docker compose build` should be run before release.
- Browser tests (`e2e/`, Playwright) are read-only smoke tests of the live screens per persona. Write flows in the browser, accessibility and visual checks are not automated. No frontend unit tests.
