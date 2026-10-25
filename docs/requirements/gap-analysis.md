# BusineX AI Edu Lab — Feature Gap Analysis

## Status definitions

- **Implemented:** Production behavior exists and is verified.
- **Prototype:** Interactive frontend exists with sample/local data.
- **Partial:** Some production behavior exists, but required controls are incomplete.
- **Missing:** No implementation found.

No requested production module is currently classified as implemented because the repository has no backend, persistence, authentication, or automated tests.

## Ten-gap assessment

| # | Operational gap | Existing state | Required state | Status | Priority |
|---:|---|---|---|---|---|
| 1 | Multi-tenant foundation and RBAC | Tenant/security screens and role switcher | Authenticated memberships, seven roles, tenant-scoped APIs, RLS, recovery, audit | Prototype | P0 |
| 2 | AI question-bank intelligence | Syllabus assessment builder and review UI | Upload/extract/classify/deduplicate/generate/version/approve/export with provenance | Prototype | P0 after foundation |
| 3 | AI Study Buddy | Deep conversational and citation UI | Tenant-isolated RAG, provider gateway, safety, metering, multilingual/voice, retention | Prototype | P1 |
| 4 | Daily quizzes and adaptive practice | Adaptive practice and live quiz UI | Scheduler, DQ publishing, attempts, deterministic grading, retries, recommendations | Prototype | P1 |
| 5 | Academic analytics and predictions | Rich dashboards and advisory labels | Trusted event pipeline, metric definitions, explainable models, monitoring | Prototype | P1 |
| 6 | AI-assisted assignment evaluation | Two-level assignment/evidence/review UI | Secure submissions, rubric engine, AI drafts, moderation, durable approvals | Prototype | P1 |
| 7 | Automated results | Interactive gradebook and assessment-results prototype | Exam setup, deterministic weights, marks import, report cards, corrections, history | Prototype | P1 |
| 8 | Gamification | XP, DQ, challenges, leaderboards, streaks, rewards, live quiz UI | Durable event ledger, rules, privacy controls, realtime sessions | Prototype | P2 |
| 9 | TCO, AI usage, subscription, billing | Administration/usage mock data | Usage ledger, configurable rates, quotas, plans, allocations, invoices, reconciliation | Missing | P1 |
| 10 | Production security, DevSecOps, QA | Security command-center UI | CI/CD, secrets, encryption, scans, backups, observability, automated tests | Missing | P0 |

## Detailed requirement matrix

### Foundation and institution management

| Requirement | Current | Gap |
|---|---|---|
| Institution onboarding/profile/branding | UI concepts | No API, persistence, validation, workflow |
| Academic years/departments/classes/batches/sections | Navigation concepts | No normalized model or CRUD |
| Courses/subjects/chapters/syllabus | Course and syllabus UI | No persisted curriculum/versioning |
| Plans and quotas | UI concepts | No quota enforcement or ledger |
| Institution isolation | Architecture visualization | No trusted tenant context or RLS |
| Seven required roles | Four simulated roles | Principal and Evaluator absent; no real assignments |
| Password/OTP recovery | Missing | Identity provider and recovery flow required |
| Audit logging | UI stream only | No append-only server audit |

### QuestionBankAI

| Requirement | Current | Gap |
|---|---|---|
| PDF/DOCX/XLSX/CSV ingestion | Missing | Upload, scanning, parsers, async jobs |
| Extraction and answer parsing | Missing | Structured extraction pipeline |
| Duplicate detection | Missing | Exact hash and embedding similarity |
| Curriculum classification | Mock syllabus mapping | Persisted taxonomy and confidence |
| Difficulty/Bloom classification | Form controls and labels | Validated model outputs and review |
| Question generation | Static generated examples | Model gateway, schema validation, provenance |
| Versions and approvals | UI approval state | Durable immutable versions and reviewer records |
| Export | Buttons only | Authorized export jobs and files |

### AIStudyBuddy

| Requirement | Current | Gap |
|---|---|---|
| Contextual chat | Interactive local prototype | API, durable conversation, streaming |
| Grounded retrieval/citations | Static citations | Ingestion, ACL-aware retrieval, citation verification |
| Multilingual/voice | Missing | Language policy, STT/TTS adapters, metering |
| Usage limits | UI concepts | Atomic quota checks and usage ledger |
| Prompt injection protection | Missing | Input/context separation, classifiers, output checks |
| Tenant isolation | UI concept | Retrieval and persistence enforcement |

### QuizPracticeEngine

| Requirement | Current | Gap |
|---|---|---|
| Daily scheduling | Planner UI | Durable schedules, timezone handling, idempotency |
| Question selection/randomization | Static samples | Seeded selection and version snapshot |
| Attempts and answers | Local state | Durable attempt lifecycle |
| Objective grading | Static feedback | Deterministic grading service |
| Adaptive recommendations | Prototype | Policy engine with evidence and evaluation |
| Live quiz | Complete frontend simulation | Realtime server, presence, durable sessions |

### AcademicIntelligence

| Requirement | Current | Gap |
|---|---|---|
| Student/teacher/institution dashboards | Prototype | Trusted metrics, API, authorization |
| Risk indicators | Advisory sample UI | Feature definitions, training/evaluation, monitoring |
| Confidence and explanations | UI present | Computed provenance and calibration |
| Fairness and intervention control | UI present | Governance, audit, override persistence |

### Assignments and AIEvaluationEngine

| Requirement | Current | Gap |
|---|---|---|
| Creation/scheduling | Prototype | CRUD, timezone/deadline rules |
| Submissions | Sample rows | Secure uploads, versioned submissions |
| Rubrics | Prototype | Persisted criteria and deterministic score calculation |
| AI feedback | Static recommendation | Provider gateway, provenance, structured draft |
| Similarity review | Responsible review UI | Permitted provider integration and policy controls |
| Teacher moderation | Local approval state | Durable approval and immutable history |
| Resubmission/projects | UI concepts | Workflow state machine |

### ResultManagement

All production requirements are missing: exam configuration, marks import, deterministic grade calculation, weighting, report-card PDF, logo/photo/signature assets, bulk export, publishing, correction, audit, and history.

### LearningGamification

The frontend covers the requested experiences and additional DQ/live-quiz concepts. Missing production elements are the XP ledger, idempotent award rules, badge definitions and evidence, streak timezone logic, privacy preferences, realtime service, abuse prevention, and audit.

### InstitutionBillingAndUsage

All production ledger and billing requirements are missing. Prices must be effective-dated configuration records. Estimated allocations and provider-billed actuals must remain separate. Financial calculations require immutable inputs, reconciliation, and independent tests.

### UI/UX

| Requirement | Current | Gap |
|---|---|---|
| Modern responsive UI | Strong prototype | Preserve |
| Working navigation | Broad local-state navigation across most prototype modules | URL routing, deep links, route guards, and automated route coverage |
| List/detail views | Many interactive prototype modules | API-backed state for every required menu |
| Search/filter/pagination | Several local-state search and filter demos; no reusable pagination | Query contracts, durable filters, server pagination |
| Create/edit/archive | Many local-state demos | Validated persisted workflows, conflict handling, audit |
| Role visibility | Four-role client rules | Server authorization and seven roles |
| Loading/empty/error states | Mostly absent | Standard async-state components |
| Accessibility | Some semantic structure | Automated/manual WCAG review |
| No nonfunctional buttons | Not met | Inventory and wire or remove every action |

## P0 acceptance criteria

The first production milestone is complete only when:

1. A user authenticates through one approved identity system.
2. The API derives actor and institution context from trusted credentials.
3. Institution, user membership, role assignment, and audit tables exist.
4. PostgreSQL RLS is enabled and forced on tenant-owned P0 tables.
5. Cross-institution API and direct database tests prove denial.
6. Platform and institution admins can create/manage institutions and memberships within scope.
7. The frontend uses typed APIs for the selected vertical slice.
8. Mutations emit auditable actor, institution, action, resource, and request metadata.
9. CI runs formatting, typing, tests, security scans, and migration checks.
10. Setup and recovery procedures are documented and verified.

## Nonfunctional risks

| Risk | Impact | Mitigation |
|---|---|---|
| Prototype mistaken for production behavior | Security/compliance misrepresentation | Maintain explicit prototype/sample labels and completion reports |
| Tenant leakage | Critical | Trusted tenant context, RLS, scoped storage, negative tests |
| Monolithic frontend | Delivery speed and bundle size | Feature extraction and route-level code splitting |
| AI hallucination or ungrounded output | Academic quality | Retrieval provenance, schemas, safety checks, human approval |
| AI/provider cost spikes | Financial | Budgets, rate limits, metering, cost-aware routing |
| Unreliable scheduled jobs | Missed quizzes/billing errors | Outbox, idempotency, retries, reconciliation |
| Grade calculation defects | High-stakes learner impact | Pure deterministic engine, golden tests, versioned policies |
| Proctoring privacy harm | Legal/trust | Data minimization, explicit consent, short retention, human review |
| Scope breadth | Schedule risk | Vertical slices and strict P0/P1/P2 gates |
| Indian privacy obligations change | Compliance risk | Configurable policy and legal review at release |
