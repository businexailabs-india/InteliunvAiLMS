# BusineX AI Edu Lab — Target Architecture

## Architecture decision

Preserve the existing React/Vite frontend and evolve it into a modular client. Add production services alongside it rather than replacing the working prototype.

The target product name is BusineX AI Edu Lab. Existing IntelUniVen UI references remain a migration concern until brand ownership, assets, legal text, and rollout compatibility are confirmed.

### Confirmed foundation decisions

- **Identity:** provider-neutral OIDC/SAML contract, with Keycloak as the development identity provider.
- **Deployment:** cloud-neutral containers first; cloud-specific Terraform composition follows after a production cloud is selected.
- **Backend baseline:** FastAPI modular monolith, PostgreSQL with forced RLS, Redis-compatible cache/queue, and OpenAPI-derived frontend contracts.
- **Brand migration:** unresolved. Preserve current UI branding until product assets and rollout scope are approved; target architecture and new production modules use the BusineX name.

Recommended initial topology:

```text
React/Vite Web Client
        |
API Gateway / Load Balancer
        |
FastAPI Modular Monolith
  |        |         |          |
PostgreSQL Redis   S3 Adapter   AI Gateway
 + pgvector         |            |
  |              File Scan    LLM/Embedding Providers
  |
Outbox + Worker/Scheduler
        |
Analytics/Event Pipeline
```

A modular monolith is preferred for the first production release. It keeps authorization, transactions, and tenant enforcement coherent while allowing high-load capabilities—AI jobs, document extraction, realtime quiz sessions, analytics—to separate later.

## Proposed repository evolution

```text
.
├── src/                         # Existing React client, incrementally modularized
│   ├── app/
│   ├── features/
│   ├── components/
│   ├── api/
│   └── ...
├── services/
│   ├── api/                     # FastAPI application
│   │   ├── app/
│   │   │   ├── auth/
│   │   │   ├── tenancy/
│   │   │   ├── academics/
│   │   │   ├── questions/
│   │   │   ├── quizzes/
│   │   │   ├── assignments/
│   │   │   ├── results/
│   │   │   ├── ai/
│   │   │   ├── billing/
│   │   │   └── audit/
│   │   ├── migrations/
│   │   └── tests/
│   └── worker/                  # Background tasks and schedules
├── packages/
│   ├── contracts/               # OpenAPI-derived TypeScript types
│   └── ui/                      # Extracted local design primitives, when justified
├── infra/
│   ├── containers/
│   ├── terraform/
│   └── observability/
└── docs/
```

The precise backend framework should be confirmed before scaffolding. FastAPI is recommended because no backend exists and the platform requires strong document/AI/data tooling. This does not replace any existing production backend.

## Tenant and identity model

### Identity

- Use one identity system only.
- Support password and OTP recovery through the chosen identity provider.
- Establish an authenticated `user_id`; never trust a client-submitted role or institution.
- Resolve active institution membership server-side.
- Support Platform Super Admin, Institution Admin, Principal/Academic Director, Teacher, Student, Parent/Guardian, and Evaluator.
- Represent roles through scoped assignments rather than a single role column.

### Request tenant context

1. Validate the access token.
2. Resolve institution membership and status.
3. Select or validate the active institution.
4. Start a database transaction.
5. Set transaction-local actor and institution context.
6. Apply service authorization.
7. Rely on PostgreSQL row-level security as defense in depth.
8. Append an audit event for sensitive reads and all mutations.

Tenant IDs must never be inferred only from URL parameters.

## Application modules

| Bounded context | Responsibilities |
|---|---|
| Identity & Access | Authentication integration, memberships, roles, permissions, recovery |
| Tenancy | Institutions, branding, settings, plans, quotas, regions |
| Academic Structure | Years, terms, departments, programs, classes, batches, sections |
| Curriculum | Courses, subjects, chapters, syllabus, outcomes, resources |
| QuestionBankAI | Ingestion, extraction, classification, generation, versions, approvals |
| QuizPracticeEngine | Schedules, selection, attempts, answers, grading, adaptive recommendations |
| AIStudyBuddy | Conversations, retrieval, citations, safety, budgets, retention |
| Assignments | Assignments, submissions, rubrics, evaluation, resubmission |
| AIEvaluationEngine | Draft analysis and feedback, moderation, approval history |
| ResultManagement | Exams, marks, deterministic calculations, report cards, corrections |
| AcademicIntelligence | Progress, verified metrics, advisory risk indicators, model monitoring |
| LearningGamification | XP ledger, badges, streaks, challenges, live quiz sessions |
| Billing & Usage | Metering, quotas, prices, allocations, invoices, reconciliation |
| Governance | Audit, consent, privacy rights, retention, AI governance |

## API strategy

- Version APIs under `/api/v1`.
- Use OpenAPI as the contract source.
- Generate frontend types/client bindings from OpenAPI.
- Use cursor pagination for large mutable collections.
- Require idempotency keys for externally retried mutations and scheduled operations.
- Use optimistic concurrency (`version` or ETag) for authored content and question versions.
- Return consistent problem details for validation, authorization, conflict, and quota failures.
- Never expose provider credentials, internal prompts, cross-tenant IDs, or raw model traces.

## Data and storage

### PostgreSQL

- Source of truth for transactional and configuration data.
- UUID primary keys.
- `institution_id` on every tenant-owned row.
- Foreign keys include or validate institution ownership.
- Row-level security enabled and forced for tenant-owned tables.
- Partial and composite indexes support tenant-scoped access.
- Append-only ledgers for AI usage, grades, gamification points, billing, and audit.

### Object storage

- S3-compatible abstraction with institution-prefixed object keys.
- Private buckets only; short-lived signed URLs.
- MIME allowlists, size limits, checksum validation, malware scanning, quarantine.
- Metadata stored in PostgreSQL; object lifecycle follows retention policy.
- Separate classes for learning content, submissions, exports, report cards, and restricted proctoring evidence.

### Vector retrieval

- Start with pgvector to keep tenant enforcement close to PostgreSQL.
- Store `institution_id`, resource ACL metadata, source version, and embedding model with each chunk.
- Filter by institution and authorization before similarity ordering.
- Do not embed restricted data unless policy permits it.

## AI architecture

```text
Feature service
  -> Prompt registry and version
  -> Policy/consent/quota check
  -> Tenant-scoped retrieval
  -> Prompt-injection filtering and context labeling
  -> Provider-independent model gateway
  -> Structured output validation
  -> Safety validation
  -> Persist provenance, usage, and review state
```

Required properties:

- Provider abstraction and cost-aware routing
- Configurable pricing; no hardcoded provider rates
- Structured JSON schemas for generated artifacts
- Prompt and model versioning
- Source provenance and citations
- Token/request/voice/embedding metering
- Per-tenant and per-user budgets and rate limits
- Mock provider for deterministic tests
- Human approval before publishing questions, feedback, grades, interventions, or high-stakes outputs

## Background work and realtime

- Redis-backed queue and cache abstraction.
- Worker tasks for extraction, embeddings, generation, exports, notifications, and analytics aggregation.
- Scheduler for daily quizzes, retention, reconciliations, and reminders.
- Transactional outbox prevents lost events.
- Idempotency table and unique business keys make retries safe.
- Realtime gateway supports live quizzes and proctoring events; PostgreSQL remains the durable source of truth.

## Security and privacy

- TLS, secure headers, CSRF strategy appropriate to the authentication mechanism.
- Least-privilege service identities and secret manager integration.
- Encryption at rest plus tenant-aware application encryption for designated fields.
- MFA for privileged roles.
- Short-lived scoped access for evaluators.
- Immutable or tamper-evident audit export.
- Consent, purpose limitation, data minimization, correction, export, deletion, and retention workflows.
- Age-appropriate design and guardian consent where applicable.
- Indian privacy review must include the Digital Personal Data Protection Act, 2023 and rules in force at implementation time; legal counsel must validate policy decisions.
- Proctoring cannot use facial recognition, emotion inference, or automatic misconduct decisions without a separately approved legal and ethical design.

## Deployment model

- Containerized API and workers.
- Managed PostgreSQL, Redis-compatible cache, and object storage.
- Cloud adapters for AWS, Azure, or GCP.
- Terraform modules with environment-specific composition.
- Separate development, staging, and production accounts/projects.
- Automated backups and restore drills.
- OpenTelemetry traces, metrics, logs, and correlation IDs.
- SLOs for API availability, background job delay, AI gateway error rate, and billing reconciliation.

## Quality gates

- Formatting and strict type checking
- Unit tests for deterministic domain logic
- Integration tests against PostgreSQL with RLS enabled
- API contract tests
- Cross-tenant negative tests
- E2E tests for critical workflows
- Accessibility checks
- Dependency, secret, container, and IaC scanning
- Migration forward/backward compatibility review

## Migration from prototype

1. Preserve the current UI and route behavior.
2. Introduce browser routing and feature boundaries without visual changes.
3. Add typed API interfaces behind mock adapters.
4. Build the tenancy/auth foundation and replace mock role switching in protected environments.
5. Replace one vertical slice at a time with persisted APIs.
6. Keep sample/demo mode explicit until a screen is connected to trusted data.
7. Add route-level code splitting as screens move into feature modules.
