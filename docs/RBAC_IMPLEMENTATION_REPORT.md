# RBAC implementation report

This pass moves billing, gamification, proctoring, and the main academic reads onto the permission registry in `services/api/app/security/permissions.py`, and it limits teacher grading to an active course assignment.

## 1. Files changed

- `services/api/app/security/permissions.py` — new grants for billing reads that principals already had, plus `gamification:read`, `gamification:play`, and `proctoring:participate`. `proctoring:review` was removed from the support agent.
- `services/api/app/security/rbac.py` — `require_any_permission` and `require_all_permissions`.
- `services/api/app/security/scope.py` — course visibility, teaching-assignment checks, and batch-grade rejection.
- `services/api/app/models.py` — `CourseInstructor`.
- `services/api/migrations/versions/0010_course_instructors.py` — table, host backfill, forced row-level security, grant to `businex_app`.
- `services/api/app/api/v1/billing.py` — `billing:read`, `billing:manage`, and `institution:manage_all`.
- `services/api/app/api/v1/engagement.py` — gamification audience, practice scoring, proctoring ownership, legacy billing.
- `services/api/app/api/v1/academics.py` — grade, submissions, attendance, roster, classes, directory.
- `services/api/app/api/v1/lms.py` — course lists, lessons, learning paths, dashboard, assessments, results, attendance, enrollments, cohorts, teaching notes, instructor assign and revoke.
- `services/api/app/api/v1/ai.py` — adaptive learning, student success, AI usage.
- `services/api/app/api/v1/training.py` — completion report also requires `analytics:read`.
- `services/api/tests/test_permissions.py`, `services/api/tests/test_course_scope.py`, `services/api/tests/test_rls.py`.
- `src/access.ts` — Gamification menu requires `gamification:read` when the session permission list is present.
- `docs/RBAC.md`.

## 2. Routes moved off legacy role lists

Billing catalogue, checkout, subscription changes, invoices, payments, usage, entitlements, refunds, and the legacy `/billing` and `/billing/ai-quota` routes now call `require_permission`. Platform admin billing routes call `institution:manage_all`. Stripe, Razorpay, and PayPal webhooks still verify the provider signature and were not switched to a browser session.

Gamification, practice submit, practice play, proctoring start, proctoring events, proctoring review, and the proctoring list now use `gamification:*` or `proctoring:*`.

Course, lesson, assignment, assessment, attendance, result, class, cohort, and AI usage reads require the matching permission and then filter by enrollment, parent link, or teaching assignment.

Some handlers still call `require_any` before `require_permission`. The permission check is the deny-by-default gate. `require_any` no longer decides billing, grading scope, or proctoring review by itself.

## 3. Permission identifiers

Added to the existing registry:

- `gamification:read` — student, teacher, corporate trainer, parent, coordinator, and roles that include those sets.
- `gamification:play` — student.
- `proctoring:participate` — student.

Removed:

- `proctoring:review` from `support_officer`.

`billing:read`, `billing:manage`, and `institution:manage_all` were already defined. Billing routes now use them instead of `BILLING_ROLES`.

## 4. Course-assignment enforcement

`assignment:grade` is no longer enough for a teacher. `grade_submission` loads the submission and its assignment in the token's institution, then requires an active `course_instructors` row unless the role is coordinator, principal, institution admin, or platform super admin. The same helper covers submission lists, attendance recording, class scheduling, and roster reads.

Creating a course assigns the creator. Scheduling a class assigns the host only after that person can already see the course. Revoking a row sets `active` to false. Migration `0010` copies distinct class hosts and does not grant every teacher every course.

There is no batch-grade HTTP route. `authorize_grade_batch` returns false when any row is unassigned for a teacher, so a mixed batch is rejected as a whole. Unit tests cover that helper. They do not execute a database transaction.

## 5. Tenant isolation and row-level security

Application queries keep filtering on the institution from the token. Cross-tenant course and session lookups return 404. A same-institution teacher who is not assigned receives 403.

`course_instructors` enables and forces row-level security with the same `app.institution_id` policy as the other tenant tables. The host backfill runs before `FORCE ROW LEVEL SECURITY`, while the migration role can still write. Ordinary API sessions use `businex_app` and the request context set in `app/db.py`.

`tests/test_rls.py` includes `course_instructors` in the tenant-table list. Those tests were not executed against Postgres in this session.

## 6. Database migrations

`0010_course_instructors` revises `0009`. It creates `course_instructors`, backfills hosts from `scheduled_classes`, enables and forces row-level security, and grants the table to `businex_app`. Downgrade drops the table. It does not drop courses, grades, billing rows, or proctoring rows.

This session did not apply the migration to a running database.

## 7. Tests executed

Command, from `services/api`:

```text
python -m pytest --tb=line -q --override-ini addopts=
```

Result: **157 passed, 16 skipped, 0 failed** in 7.76s.

Skipped:

- 13 tests in `tests/test_rls.py`: `database unavailable: InvalidPasswordError`.
- 3 tests in `tests/test_live_stack.py`: API not reachable at `http://localhost:8000`.

`tests/test_course_scope.py` and the added rows in `tests/test_permissions.py` passed inside that run. They check permission resolution and the course-assignment rule in process. They do not open a second institution in Postgres.

No frontend test command was run. This workspace has no local `node_modules` test pass for `src/access.ts`.

## 8. Known gaps

- Row-level security was not re-proven against two live institutions. The policies are in the migrations; the integration tests skipped because the local database rejected the password.
- Grade, billing, and proctoring denial paths do not have HTTP tests against a database in this run.
- Several write routes still mention a role set and a permission together. The permission is what denies a student or a finance admin.
- Support agents can still read course titles because they hold `course:read`. They cannot review proctoring evidence.
- Question-bank list and some training authoring routes are still role-gated, with `content:review` already required on approval.
- The sample Class Analytics screen and Study Buddy token-overlap search were left as they were.
- No camera, microphone, or identity-collection behavior was added.
- The live site at https://ailms-app.34.180.38.27.sslip.io was rebuilt on 27 Oct 2026. Health returned `ok`, `demo`, `gemini`. Alembic is at `0010`. `course_instructors` exists. The web bundle is `index-CPWpyZ6m.js`. A teacher login includes `assignment:grade` and not `billing:manage`. A student login does not include `course:create`, and creating a course or listing invoices returned 403. The VM environment file was not replaced.

## 9. Deployment and rollback

Deploy by building the API image so migration `0010` runs on startup, then publishing the web bundle. Do not copy `config.example.env` over the VM environment. After the web deploy, hard-refresh the browser.

Rollback the application revision, then run `alembic downgrade 0009` if `0010` has been applied. That drops `course_instructors` only. Grades, subscriptions, and proctoring rows stay. Teachers would again be limited only by the previous release's checks once that code is restored.
