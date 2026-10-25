# BusineX AI Edu Lab — Logical Data Model

## Modeling conventions

- PostgreSQL is the transactional source of truth.
- Primary keys are UUIDs.
- Every tenant-owned table has a non-null `institution_id`.
- Global/platform tables are explicitly identified and contain no tenant-private payload.
- Timestamps use UTC `timestamptz`.
- Mutable authored entities use `version`, `created_at`, `updated_at`, and actor IDs.
- Soft deletion is used only where recovery or audit requires it; financial, grade, AI usage, and audit ledgers are append-only.
- User-entered display identifiers are separate from primary keys.
- Sensitive fields are classified and encrypted when database/storage encryption is insufficient.
- Foreign-key relationships must not permit cross-institution references.

## Tenant enforcement

The API sets transaction-local context after authenticating and authorizing membership:

```sql
select set_config('app.user_id', :user_id, true);
select set_config('app.institution_id', :institution_id, true);
```

Representative policy:

```sql
alter table courses enable row level security;
alter table courses force row level security;

create policy courses_tenant_isolation on courses
using (institution_id = nullif(current_setting('app.institution_id', true), '')::uuid)
with check (institution_id = nullif(current_setting('app.institution_id', true), '')::uuid);
```

The application database role must not own tenant tables and must not have `BYPASSRLS`.

For important parent-child relations, use composite uniqueness and foreign keys such as `(institution_id, id)` so a child cannot reference a parent in another institution.

## Core tenancy and identity

| Table | Purpose | Key constraints/indexes |
|---|---|---|
| `institutions` | Tenant root, profile, branding, region, status | unique slug; plan/status indexes |
| `institution_settings` | Versioned tenant configuration | unique institution + key + version |
| `academic_years` | Tenant academic calendars | unique institution + code |
| `users` | Application profile linked to external identity | unique identity-provider subject; no single role column |
| `institution_memberships` | User membership in a tenant | unique institution + user; status index |
| `roles` | Global system roles and tenant custom roles | unique scope + code |
| `permissions` | Stable permission catalog | unique code |
| `role_permissions` | Permission composition | unique role + permission |
| `user_role_assignments` | Scoped role grants | institution, user, role, optional resource scope; effective dates |
| `account_recovery_events` | Recovery audit metadata | actor/subject/time indexes; no OTP plaintext |
| `audit_logs` | Append-only security and business audit | institution + occurred_at; actor; resource; correlation ID |

Required role codes:

- `platform_super_admin`
- `institution_admin`
- `principal_academic_director`
- `teacher`
- `student`
- `parent_guardian`
- `evaluator`

## Academic structure

| Table | Purpose |
|---|---|
| `departments` | Academic/organizational departments |
| `programs` | Programs, grades, degrees, or training tracks |
| `classes` | Academic class/cohort definition |
| `batches` | Intake or cohort grouping |
| `sections` | Section within class/batch |
| `terms` | Terms/semesters within an academic year |
| `students` | Student-specific profile linked to user where applicable |
| `teachers` | Teacher/faculty-specific profile |
| `guardians` | Guardian profile |
| `student_guardians` | Authorized student-guardian relationship |
| `courses` | Course identity and lifecycle |
| `course_offerings` | Course delivery in term/section with faculty |
| `subjects` | Subject taxonomy |
| `chapters` | Ordered curriculum hierarchy |
| `syllabi` | Approved syllabus versions |
| `learning_outcomes` | Coded measurable outcomes |
| `syllabus_outcomes` | Outcome mapping and required weight |
| `enrollments` | Student participation in offering |
| `learning_resources` | Metadata and ACL for content stored in object storage |
| `resource_versions` | Immutable versions, checksums, source, approval |

## QuestionBankAI

| Table | Purpose |
|---|---|
| `question_sources` | Uploaded source file metadata, checksum, extraction status |
| `source_chunks` | Parsed chunks with source locations and optional embeddings |
| `questions` | Stable question identity and current status |
| `question_versions` | Immutable content, answer, explanation, type, difficulty, Bloom level |
| `question_taxonomy_links` | Course/subject/chapter/topic/outcome mappings |
| `question_duplicate_candidates` | Exact/near-duplicate evidence and review decision |
| `question_approvals` | Reviewer, decision, comments, approved version |
| `question_generation_jobs` | Prompt/model/schema status and source scope |
| `question_exports` | Authorized export job and generated object |

`question_versions` stores provenance fields including:

- `model_provider`
- `model_name`
- `prompt_template_id`
- `prompt_version`
- `structured_output_schema_version`
- `source_material_refs`
- `input_tokens`
- `output_tokens`
- `estimated_cost_amount`
- `review_status`

## QuizPracticeEngine

| Table | Purpose |
|---|---|
| `quizzes` | Quiz definition, mode, policy, lifecycle |
| `quiz_versions` | Immutable instructions, settings, grading policy |
| `quiz_questions` | Ordered question-version snapshot and points |
| `quiz_schedules` | Timezone-aware scheduled publication |
| `quiz_publication_runs` | Idempotent scheduler run record |
| `quiz_attempts` | Learner attempt lifecycle and policy snapshot |
| `quiz_answers` | Submitted answer, timing metadata, awarded points |
| `quiz_grading_events` | Append-only deterministic grading decisions |
| `practice_recommendations` | Advisory recommendation, evidence, confidence, disposition |

Unique idempotency keys are required for schedule publication and attempt finalization.

## Assignments and evaluation

| Table | Purpose |
|---|---|
| `assignments` | Stable assignment identity |
| `assignment_versions` | Instructions, outcomes, deadlines, policy |
| `assignment_publications` | Audience and release state |
| `submissions` | Submission lifecycle |
| `submission_versions` | Immutable file/text versions and checksums |
| `evaluation_rubrics` | Rubric identity |
| `rubric_versions` | Criteria, levels, point rules |
| `evaluation_reviews` | Human/AI draft reviews and moderation |
| `evaluation_scores` | Criterion scores tied to rubric version |
| `feedback_items` | Draft/approved learner-facing feedback |
| `similarity_reviews` | Provider result, matched sources, human decision |

Final grades reference an authorized human approval. AI review rows cannot transition directly to a final grade.

## Results

| Table | Purpose |
|---|---|
| `exams` | Exam identity and offering scope |
| `exam_components` | Weighted components and rules |
| `marks_imports` | Source file, validation, reviewer, status |
| `grades` | Versioned calculated grade outcome |
| `grade_calculation_runs` | Inputs, policy version, deterministic output hash |
| `grade_corrections` | Append-only correction request and approval |
| `report_cards` | Generated report-card version and storage reference |
| `result_publications` | Audience, publication time, actor |
| `academic_history` | Durable learner result history |

Decimal precision and rounding mode must be explicit in each grading policy. Calculation code must be pure and independently testable.

## AI Study Buddy and AI governance

| Table | Purpose |
|---|---|
| `ai_conversations` | Tenant/user/course context and retention policy |
| `ai_messages` | User/assistant/tool messages and safety status |
| `ai_citations` | Message-to-authorized-source references |
| `ai_prompt_templates` | Versioned prompt registry |
| `ai_model_routes` | Policy-driven model selection |
| `ai_generation_requests` | Request lifecycle, provenance, schema validation |
| `ai_usage_events` | Append-only tokens, requests, voice, embeddings, costs |
| `ai_budget_policies` | Tenant/user/feature budgets |
| `ai_safety_events` | Injection, policy, or output safety events |
| `embedding_records` | Model/version/chunk embedding metadata |

AI usage events reference effective-dated pricing but retain the rate snapshot used for the estimate.

## Progress, analytics, and predictions

| Table | Purpose |
|---|---|
| `learning_events` | Append-only normalized learning telemetry |
| `student_progress` | Materialized/derived course and outcome progress |
| `mastery_estimates` | Model version, evidence window, estimate, uncertainty |
| `academic_risk_indicators` | Advisory indicator, evidence, confidence, review state |
| `interventions` | Human-created support workflow |
| `intervention_outcomes` | Observed follow-up indicators without causal claims |
| `analytics_metric_definitions` | Versioned metric contracts |
| `analytics_snapshots` | Reproducible aggregate values |

Sensitive predictions must have expiry, evidence, model version, reviewer disposition, and an override/audit path.

## Gamification

| Table | Purpose |
|---|---|
| `gamification_rules` | Versioned award rules |
| `points_ledger` | Append-only XP/point transactions |
| `badges` | Badge definition and evidence policy |
| `student_achievements` | Earned badge/achievement and verifier |
| `challenges` | Challenge definition and availability |
| `challenge_progress` | Learner/team progress |
| `learning_streak_events` | Qualifying day events and timezone |
| `leaderboard_preferences` | Opt-in, pseudonym, audience |
| `rewards` | Reward definition and constraints |
| `reward_redemptions` | Audited redemption lifecycle |
| `live_quiz_sessions` | Realtime game session and settings |
| `live_quiz_participants` | Session-scoped identity/pseudonym |
| `live_quiz_responses` | Question-version response and score |

Points are awarded with unique source event IDs so retries cannot duplicate rewards.

## Subscriptions, quotas, usage, and billing

| Table | Purpose |
|---|---|
| `subscription_plans` | Versioned Starter/Professional/Enterprise/University definitions |
| `plan_entitlements` | Seats, storage, AI, voice, and feature entitlements |
| `subscriptions` | Institution plan and billing lifecycle |
| `usage_quotas` | Effective quota policy and period |
| `usage_counters` | Atomic current-period enforcement counters |
| `storage_usage` | Metered object/video/database storage |
| `provider_pricing` | Effective-dated provider-specific rates |
| `institution_cost_allocations` | Estimated allocated compute/database/storage/network/support |
| `provider_charge_imports` | Actual provider billing source |
| `cost_reconciliations` | Estimated-to-actual reconciliation |
| `invoices` | Invoice header and status |
| `invoice_lines` | Seats, base fees, usage, overages, credits |
| `payments` | Payment-provider references and state |

Never overwrite historical prices, quota policies, invoices, usage, or allocation inputs.

## Privacy, consent, and retention

| Table | Purpose |
|---|---|
| `consent_policies` | Versioned purpose and required consent |
| `consent_records` | Subject/guardian decision and evidence |
| `privacy_requests` | Access, correction, export, deletion workflow |
| `retention_policies` | Institution/data-class retention |
| `retention_runs` | Idempotent deletion/anonymization jobs |
| `data_exports` | Authorized subject/admin export |
| `legal_holds` | Scoped retention override |
| `proctoring_sessions` | Consent and monitoring policy snapshot |
| `proctoring_events` | Restricted observed events |
| `proctoring_reviews` | Authorized human decision and notes |

## Index strategy

Baseline indexes for tenant tables:

- `(institution_id, id)` unique
- `(institution_id, created_at desc)`
- `(institution_id, status, updated_at desc)` for workflow queues
- `(institution_id, external/display code)` unique where applicable
- Join-table unique constraints preventing duplicate assignments
- Partial indexes for active/pending records
- GIN indexes only for validated search needs
- pgvector indexes partitioned or filtered to preserve tenant-safe retrieval behavior

Index design must be verified with representative query plans; avoid speculative indexes on every column.

## Deletion and archival

- Institution deletion is a controlled offboarding workflow, not a cascade initiated from the UI.
- Legal/financial/audit records follow retention and anonymization policies.
- Authored content uses archive states and immutable published versions.
- Object deletion is coordinated with database state through outbox events and reconciliation.
- Backups have separate expiration and restore procedures.
