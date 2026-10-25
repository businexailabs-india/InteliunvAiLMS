# Test Plan - IntelUniVen AI Edu Lab

Version 1.0 - 24 Oct 2026. Scope is the current repository state (React frontend, FastAPI backend,
PostgreSQL with row-level security, Redis, Keycloak, Docker Compose). Test cases live in
[test-cases.md](test-cases.md).

## 1. Objectives

1. Show that each of the ten business scenarios works end to end against persistent data.
2. Show that tenant isolation holds at both the API and the database level.
3. Show that role-based access, audit logging and human-approval rules cannot be bypassed.
4. Show that the frontend screens connected to the API handle loading, error, empty and forbidden
   states, and that prototype mode still works.
5. Be honest about what is not covered. Gaps are listed in section 9.

## 2. Scope

### In scope

| Area | Items |
|---|---|
| Authentication | Demo login, token validation, forged and missing tokens, inactive users |
| Authorization | 12-role RBAC matrix, learner-only and parent-link scoping |
| Tenancy | Forced RLS, cross-tenant API denial, directory and roster scoping |
| LMS | Courses, lessons, progress, enrollments, dashboard |
| Assessment | Question bank, four-eyes approval, quiz from bank, grading, results, adjustments, scorecards |
| Academics | Assignments, submissions, grading, attendance record and correction, roster, gradebook |
| Corporate | Cohorts, members, auto-enrollment, completion report, directory |
| AI | Study Buddy, Teacher Copilot, quota, provider adapters, mock labelling |
| Engagement | XP, rank, leaderboard, proctoring review |
| Billing | Plan, invoices, AI quota administration |
| Data | Synthetic import, idempotency, hygiene (no real PII) |
| Frontend | The live screens in `src/live/*` plus routing in `App.tsx` |
| Platform | Docker Compose start-up, migrations, health, proxy, build |

### Out of scope or not yet testable

Keycloak browser login flow (not built), pgvector retrieval (not built), MinIO uploads (not
built), badges and streaks (not built), real LLM output quality (no keys), the static prototype
screens, production load and disaster recovery.

## 3. Test levels and approach

| Level | Tooling | Where | Status |
|---|---|---|---|
| Unit | pytest | `services/api/tests/test_grading.py`, `test_rbac.py`, `test_ai_providers.py`, `test_ai_adapters.py` | Automated |
| Data hygiene | pytest | `test_synthetic_data.py` | Automated |
| Database / RLS | pytest + Postgres | `test_rls.py` | Automated |
| API scenario | httpx script | `scripts/verify_integration.py`, wrapped by `test_live_stack.py` | Automated |
| Web tier smoke | httpx script | `scripts/smoke_web.py` | Automated |
| Static / build | `tsc --noEmit`, `vite build` | web container | Automated |
| UI functional | Playwright smoke per persona (`e2e/`, 29 tests); deeper flows manual | browser at http://localhost:8443 | Manual |
| Exploratory | Charter based | all roles | Manual |
| Non-functional | k6 or Locust, axe, OWASP ZAP | | Planned |

Risk-based priority: tenant isolation and RBAC first, then grading and publication integrity, then
attendance and audit trail, then AI behaviour, then UI polish.

## 4. Test environment

| Item | Value |
|---|---|
| Stack | `docker compose -f infra/containers/compose.yaml up -d` |
| API | http://localhost:8000 (OpenAPI at `/docs`) |
| Web | http://localhost:8443 |
| Database | PostgreSQL 17, role `businex_app` (RLS enforced), owner role for migrations and seed |
| Data | Starter synthetic JSON imported with `python -m app.import_seed --root /data/synthetic` |
| Auth mode | `BUSINEX_AUTH_MODE=demo`, password `Demo@2025` |
| AI | `BUSINEX_AI_PROVIDER=mock` |
| Browsers (UI) | Latest Chrome and Edge; Firefox for smoke |

Test accounts (all `@inteluniven.edu`): aarav.sharma (student), maya.chen (teacher), riya.nair
(coordinator), priya.sharma (parent), david.wilson (principal), olivia.harris (institution admin).
Synthetic users follow `demo.<role>.NNNN@example.invalid`; some are deliberately inactive.

Test data rules: only synthetic data; tests create their own records with unique names so runs are
repeatable; tests must not depend on a previous run's leftovers.

## 5. Entry and exit criteria

Entry: stack healthy (`/health` is 200), migrations at head (`0003`), seed data imported, build and
typecheck succeed.

Exit for a release candidate:

- 0 failing automated checks (scenario script, pytest suites, smoke, build).
- 100% of P0 cases executed and passed; at least 95% of P1.
- No open Critical or High defects. Medium defects have an owner and a date.
- Every gap in section 9 is either closed or accepted in writing.

## 6. Defect management

| Severity | Definition | Example | Fix target |
|---|---|---|---|
| Critical | Data leak across tenants, auth bypass, data loss | Student reads another tenant's results | Block release |
| High | Wrong grade or attendance, RBAC hole, audit missing | Score change without audit row | Block release |
| Medium | Feature broken with workaround, wrong error state | Empty state shows spinner forever | Next sprint |
| Low | Cosmetic, copy | Misaligned badge | Backlog |

Each defect records: case ID, build or commit, environment, steps, expected, actual, evidence.

## 7. Deliverables

Test plan, test cases, automated run output, defect log, and the status document
[`docs/implementation/integration-status.md`](../implementation/integration-status.md).

## 8. Roles and responsibilities

| Role | Responsibility |
|---|---|
| Developer | Unit and integration tests with each change, fix defects |
| QA | Manual UI cases, exploratory sessions, regression sign-off |
| Product owner | Accept known limitations, approve exit |
| Security reviewer | Isolation, auth and privacy cases (section 5 of cases) |

## 9. Risks and known gaps

| ID | Gap or risk | Impact | Mitigation |
|---|---|---|---|
| G1 | UI uses demo login; no Keycloak redirect flow | Production auth path untested end to end | Build OIDC UI flow, then add OIDC cases AUTH-10 to AUTH-12 |
| G2 | Real AI providers never run with keys | Adapter behaviour untested against real services | Run adapter cases with a sandbox key before release |
| G3 | No pgvector or embeddings | RAG relevance is a token-overlap stand-in | Re-baseline AI cases after pgvector |
| G4 | Playwright covers only read-only screen smoke tests; no browser write flows or frontend unit tests | Form and action regressions are caught manually | Automate the write flows in UI-01 to UI-20 |
| G5 | No badges, streaks or daily challenges | Gamification scenario is partial | Add cases when built |
| G6 | API image not rebuilt in this environment | Code in containers came from file copies | Clean `docker compose build` and rerun everything before release |
| G7 | pytest is not in the API image | Tests need manual setup | Install dev extras in CI image |
| G8 | Persona users belong to every tenant by design | Easy to mistake for a leak | Documented; use outsider users from the synthetic set for isolation cases |
| G9 | No load, accessibility or penetration testing yet | Unknown capacity and WCAG status | Section 8 of cases defines them; schedule before release |

## 10. Execution and reporting

Per cycle: bring up a clean stack, import data, run automation, execute manual P0 then P1 cases,
record results in the table in the test-cases document, review defects, decide exit.

Automation commands:

```powershell
python scripts/verify_integration.py
python scripts/smoke_web.py
python -m pytest services/api/tests/test_live_stack.py
docker exec containers-api-1 python -m pytest tests --ignore=tests/test_live_stack.py
```

Last recorded automated result (24 Oct 2026): scenario script 112 passed / 0 failed / 1 gap
(badges and streaks); unit and RLS pytest 59 passed; live-stack pytest 3 passed; web smoke 13
passed; typecheck and production build clean. Manual UI cases have not yet been executed.
