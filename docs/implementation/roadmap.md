# BusineX AI Edu Lab — Implementation Roadmap

## Delivery principles

1. Preserve the existing prototype and visual language.
2. Build production capability as vertical slices, not disconnected layers.
3. Establish tenant isolation and authorization before storing institution data.
4. Keep AI outputs in draft/review states for high-stakes workflows.
5. Treat ledgers, grades, approvals, and audit records as append-only or explicitly versioned.
6. Do not claim a module complete until APIs, persistence, security, tests, UI states, and documentation are verified.

## Priority plan

### Milestone 0 — Architecture and baseline

**Status:** Discovery documentation complete; production backend implementation not started.

Deliverables:

- Current and target architecture
- Gap analysis
- Data-model plan
- Backend decision record
- Local development and test topology
- Definition of done and security baseline

Exit criteria:

- Stakeholders approve identity-provider and backend choices.
- PostgreSQL, Redis, object storage, email/OTP, and AI-provider development strategy are confirmed.

### Milestone 1 — P0 tenant and identity vertical slice

**Foundation decisions:** provider-neutral OIDC/SAML, Keycloak for development, and cloud-neutral containers.

Modules:

- Tenancy
- Identity integration
- Memberships, roles, permissions
- Institution management
- Audit logging

Backend:

- Scaffold FastAPI service and migration tooling.
- Add health/readiness endpoints and structured request IDs.
- Implement institution, user profile, membership, role, role assignment, and audit models.
- Implement transaction-local tenant context and forced PostgreSQL RLS.
- Add institution and membership CRUD with service authorization.
- Integrate one authentication provider; do not build a competing identity store.

Frontend:

- Introduce URL routing without changing the existing visual layout.
- Create a typed API boundary and mock/real adapters.
- Replace role switching with authenticated context outside explicit demo mode.
- Connect Institution Management list/detail/create/edit/archive.
- Add loading, empty, error, forbidden, and stale-version states.

Tests:

- Authentication acceptance/rejection
- Role permission matrix
- Cross-tenant API denial
- Direct RLS denial
- Audit creation
- Institution validation and archive behavior

### Milestone 2 — P0 QuestionBankAI vertical slice

Backend:

- Secure upload metadata and quarantine.
- PDF, DOCX, XLSX, CSV extraction jobs.
- Question, version, source, approval, and taxonomy models.
- Exact and near-duplicate detection.
- AI gateway, prompt registry, structured JSON validation, provenance, and usage metering.
- Review and export workflows.

Frontend:

- Question bank list/search/filter/pagination.
- Upload and extraction status.
- Question detail/version comparison.
- AI generation/rewrite flow.
- Teacher review and approval.

Tests:

- Malformed/unsafe files
- Tenant isolation in source and question retrieval
- Deterministic mock AI outputs
- Schema rejection and retry
- Approval requirement before export/publish

### Milestone 3 — Curriculum, daily quiz, and practice

- Academic structure and curriculum CRUD
- Course, subject, chapter, syllabus, and outcomes
- Quiz definitions, schedules, attempts, answers, and deterministic grading
- Idempotent daily publication
- Revision and adaptive recommendation policies
- Teacher and learner dashboards

### Milestone 4 — AI Study Buddy

- Content ingestion and tenant-isolated pgvector retrieval
- Conversation/message retention
- Citations and source authorization
- Provider/model routing
- Prompt-injection defenses
- Quotas, cost events, and rate limits
- Optional multilingual, STT, and TTS adapters

### Milestone 5 — Assignments and AI evaluation

- Assignment schedules and secure submissions
- Rubrics and evaluation state machine
- AI draft feedback with evidence
- Teacher moderation and score approval
- Resubmissions, projects, similarity-review adapter

### Milestone 6 — Results and academic intelligence

- Exam and weight configuration
- Marks import validation
- Deterministic grade engine
- Report-card generation and publishing
- Corrections and academic history
- Verified analytics metrics
- Advisory, explainable risk indicators with monitoring

### Milestone 7 — Usage, TCO, subscriptions, and billing

- Usage events and atomic quota enforcement
- Effective-dated provider pricing
- Storage/network/compute allocations
- Subscription plans and overage policy
- Estimated-versus-actual reconciliation
- Invoice and profitability reporting

### Milestone 8 — Gamification and realtime

- XP and reward ledgers
- Badge/challenge/streak rule engine
- Privacy-safe leaderboard preferences
- Realtime live quiz gateway
- Durable sessions, presence, and result summaries
- Abuse prevention and idempotent awards

### Milestone 9 — Hardening and commercial readiness

- Accessibility conformance
- Performance and load testing
- Backup/restore drills
- Disaster recovery runbooks
- SLO dashboards and alerts
- Penetration testing and threat-model closure
- Data-protection impact assessment
- Operational support and incident processes

## First executable development task

### Task: Tenant-safe institution list vertical slice

This is the smallest executable task that proves the architecture rather than only scaffolding it.

**Backend**

1. Add `services/api` with FastAPI, settings validation, SQLAlchemy 2, Alembic, and PostgreSQL.
2. Add development containers for PostgreSQL and Redis-compatible cache.
3. Create `institutions`, `users`, `institution_memberships`, `roles`, `user_role_assignments`, and `audit_logs`.
4. Seed two institutions and users with different memberships.
5. Add forced RLS to tenant-owned membership and audit rows.
6. Implement `GET /api/v1/institutions/current` and an authorized institution-update endpoint.
7. Add request tenant context and append an audit event for updates.

**Frontend**

1. Add a typed `InstitutionService` interface.
2. Preserve a mock adapter for Figma/demo mode.
3. Add an HTTP adapter for production mode.
4. Connect the existing Institution/Tenant screen.
5. Implement loading, error, forbidden, and empty states.

**Verification**

1. A user in institution A cannot read/update institution B.
2. Changing a URL/body institution ID cannot bypass scope.
3. A direct SQL query under the application role cannot cross tenant boundaries.
4. An authorized update creates an audit record.
5. Frontend tests verify all async states.

### Dependencies requiring confirmation

- Production identity provider and final token-claim mapping; development uses Keycloak OIDC
- PostgreSQL development availability
- Python package/dependency policy
- Container support is available in the current environment; production runtime remains to be selected
- Production cloud preference and region strategy
- Transactional email/SMS provider for recovery
- Product rebranding scope from IntelUniVen to BusineX, including assets and legal copy

These choices are consequential. Backend scaffolding should begin after they are confirmed; documentation and frontend modularization can proceed independently. The recommended default, if stakeholders have no existing standards, is FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL with forced RLS, Redis-compatible queues, S3-compatible storage, OpenAPI-generated TypeScript contracts, and an external OIDC identity provider.

### Current execution status

- Repository discovery and architecture documents: complete.
- Identity and local deployment decisions: complete.
- P0 API/container scaffold: in progress.
- Production identity-provider claim mapping, cloud/region, recovery messaging provider, and BusineX rebrand scope: pending.

## Completion reporting template

For every milestone report:

| Field | Required content |
|---|---|
| Completed | Verified production behaviors |
| Partial | Implemented pieces and exact missing controls |
| Blocked | Dependency, owner, and unblock action |
| Files | Added/changed files and migrations |
| APIs | Endpoints and contracts |
| Security | Authorization, isolation, privacy, audit controls |
| Tests | Commands and passing test counts |
| Risks | Residual risks and accepted exceptions |
| Rollback | Deployment and migration rollback plan |
