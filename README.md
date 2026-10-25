# IntelUniVen AI Edu Lab

React + Vite frontend and a FastAPI / PostgreSQL backend for a multi-tenant AI learning platform.
All data in this repository is synthetic.

```
src/                    React app (App.tsx prototype shell, src/live/* screens wired to the API)
services/api/           FastAPI modular monolith, Alembic migrations, pytest suites
IntelUniVen_Backend_Starter/synthetic-data/   ~20k synthetic rows (2,000 students, 10 tenants)
infra/containers/       Docker Compose (postgres, redis, keycloak, api, worker, web)
scripts/                verify_integration.py (10 scenarios), smoke_web.py
docs/                   architecture, gap analysis, roadmap, integration status
```

## Run

```powershell
docker compose -f infra/containers/compose.yaml up -d
docker exec containers-api-1 python -m app.import_seed --root /data/synthetic   # idempotent
```

- Web: http://localhost:8443 - API docs: http://localhost:8000/docs - Keycloak: http://localhost:8080
- Demo password `Demo@2025`; users `aarav.sharma` (student), `maya.chen` (teacher), `riya.nair`
  (coordinator), `priya.sharma` (parent), `david.wilson` (principal), `olivia.harris` (admin),
  all `@inteluniven.edu`.
- Environment reference: [`.env.example`](.env.example).

## Verify

```powershell
python scripts/verify_integration.py     # business scenarios, RBAC, tenant isolation, audit
python scripts/smoke_web.py              # web tier + proxy
python -m pytest services/api/tests/test_live_stack.py
docker exec containers-api-1 python -m pytest tests    # unit + row-level security suites
```

See [docs/implementation/integration-status.md](docs/implementation/integration-status.md) for
the endpoint list, connected screens, test counts and the known limitations. Notably: AI is mocked
by default (and labelled), the UI uses demo login rather than the Keycloak redirect, retrieval is
not pgvector, and several prototype screens are still static.

## Principles

- Tenant isolation is enforced by PostgreSQL forced row-level security, not just API filters.
- Grades, attendance and proctoring outcomes change only through audited, human-approved actions.
- Proctoring signals are synthetic review aids and never disqualify a learner automatically.
