# Backend implementation plan

1. Keep existing FastAPI/Keycloak/PostgreSQL foundation; fix JWT claim mapping and tenant RLS tests before adding data.
2. Add Alembic migrations for course/module/lesson/enrollment/attendance/assessment/attempt/result and coordinator review; add service/repository tests.
3. Build authenticated `/api/v1/courses`, `/enrollments`, `/assessments`, `/attendance`, `/results` endpoints; validate tenant scope from JWT, never trust a tenant ID in request body.
4. Add `/api/v1/ai/study-buddy`, `/teacher-copilot`, `/adaptive-learning` with mock provider, tenant-specific budgets, safe RAG retrieval and usage ledger; enable live providers only with server-side secrets.
5. Add games, notifications, proctoring events and human review; store no real biometric data in fixtures.
6. Connect React screens progressively via typed adapters, replacing each local-state demo only after E2E tests pass.
7. Add billing, audit, accessibility, observability, backups, CI, rate limits, data retention, and deployment manifests.

Important: This package contains synthetic JSON and an API design supplement, not a completed production backend. Production-grade proctoring requires consent, jurisdictional privacy review, secure media handling, human appeals, and bias testing.
