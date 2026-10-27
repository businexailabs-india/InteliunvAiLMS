# Role-based access

Permissions are `resource:action` grants in `services/api/app/security/permissions.py`. The API loads role codes from `user_role_assignments` for the active institution. A request is denied unless one of those roles grants the action. Hiding a menu does not authorize the API.

Stored role codes, with the names used in this matrix:

| Requested role | Stored code |
| --- | --- |
| Platform super admin | `platform_super_admin` |
| Institution admin | `institution_admin` |
| Principal | `principal_academic_director` |
| Academic coordinator | `coordinator` |
| Teacher | `teacher` |
| Student | `student` |
| Parent / guardian | `parent_guardian` |
| Corporate trainer | `corporate_trainer` |
| Corporate HR manager | `corporate_hr` |
| Finance admin | `finance_admin` |
| Content creator | `content_creator` |
| Content reviewer | `content_reviewer` |
| Support agent | `support_officer` |
| Compliance officer | `compliance_officer` |

`content_creator` and `compliance_officer` are added to an institution the next time the API bootstrap runs.

## What the API now checks

| Action | Permission | Who has it |
| --- | --- | --- |
| Update the institution | `institution:update` | Institution admin, super admin |
| Create a course | `course:create` | Teacher, principal, institution admin, super admin |
| Create an assignment | `assignment:create` | Teacher, principal, institution admin, corporate trainer, super admin |
| Submit an assignment | `assignment:submit` | Student |
| Grade a submission | `assignment:grade` plus an active `course_instructors` row for teachers and corporate trainers | Coordinator, principal, institution admin, and super admin may grade any course in their institution. A teacher or trainer may grade only a course they are actively assigned to |
| Create an assessment | `assessment:create` | Teacher, principal, content creator, content reviewer, institution admin, super admin |
| Attempt an assessment | `assessment:attempt` | Student |
| Adjust a result | `result:update` | Coordinator, principal, institution admin, super admin |
| Approve or publish a scorecard | `result:approve`, `result:publish` | Coordinator and the roles above that include coordinator |
| Mark or correct attendance | `attendance:mark`, `attendance:update` | Teacher, coordinator, and roles that include them |
| Study Buddy | `ai:study_buddy` | Student, teacher, corporate trainer, institution admin, super admin |
| Teaching Copilot | `ai:teacher_copilot` | Teacher, corporate trainer, institution admin, super admin |
| Approve a question | `content:review` | Content reviewer, coordinator, and roles that include coordinator. The author cannot approve their own question |
| Create a batch | `cohort:manage` | Coordinator, corporate HR, and roles that include them |
| Assign a role | `user:assign_role` | Institution admin and super admin. Super admin is the only role that can grant `platform_super_admin`, and nobody can grant themselves a role they do not already hold |
| Read billing, invoices, payments, usage | `billing:read` | Finance admin, principal, institution admin, super admin |
| Change a subscription, start checkout, refund, or change the AI quota | `billing:manage` | Finance admin, institution admin, super admin |
| Edit platform plan catalogue and billing admin reports | `institution:manage_all` | Super admin |
| View own gamification standing | `gamification:read` | Student, teacher, corporate trainer, parent, coordinator, and roles that include them |
| Submit a practice game for server-scored points | `gamification:play` | Student. `POST /gamification/play` still rejects a client-supplied score |
| Start or signal the caller's own proctoring session | `proctoring:participate` | Student |
| Review proctoring for an assigned course | `proctoring:review` plus a course assignment for teachers and evaluators | Coordinator, principal, institution admin, teacher, evaluator, super admin. Support agents do not have this permission |

Login and `/api/v1/auth/me` return the permission list. The sidebar uses that list when it is present. Hidden menus are not the security boundary.

## Course assignment

`course_instructors` stores an active teaching assignment for one institution, course, and user. Creating a course assigns the creator. Scheduling a class assigns the host only when that person can already see the course. Migration `0010` copies existing class hosts and does not assign every teacher to every course.

A teacher or corporate trainer with `assignment:grade` receives 403 on a course they are not actively assigned to. The same check applies to listing that course's submissions, recording attendance, opening the roster, and reading that course's grade-related lists. A revoked row (`active = false`) removes that access. Coordinators, principals, institution admins, and the platform super admin act across courses in the token's institution only.

Institution staff who hold `course:update` or `cohort:manage` and who already cover every course may assign or revoke a teaching row: `POST /api/v1/courses/{course_id}/instructors` and `POST /api/v1/courses/{course_id}/instructors/{user_id}/revoke`.

There is no batch-grade endpoint. `authorize_grade_batch` rejects the whole set when any row is outside the caller's courses, so a future batch cannot commit a partial grade.

## Tenant scope

The API sets `app.institution_id` from the authenticated membership. Callers cannot supply it. Queries also filter on that institution. A missing or cross-tenant course, submission, or proctoring session returns 404. A caller who has the permission but is not assigned to the course returns 403.

PostgreSQL row-level security is enabled and forced on tenant tables, including `course_instructors`. The policy compares `institution_id` to `current_setting('app.institution_id', true)`. The application role is `businex_app`. Migrations run as the table owner before `FORCE ROW LEVEL SECURITY` is applied, then ordinary requests use the application role. Webhooks set a server-side billing flag and verify the provider signature. They do not accept a browser session as proof of payment.

## Billing, gamification, and proctoring

Billing reads require `billing:read`. Checkout, plan changes, cancellation, reactivation, refunds, simulated payment, and the AI quota update require `billing:manage`. Platform plan and reconciliation routes require `institution:manage_all`. Students, parents, and teachers do not receive those permissions. There is no public plan catalogue; plan rows are visible only to roles with `billing:read`.

Gamification returns the caller's own standing. Coordinators and other institution-wide academic roles see the institution board. Parents see linked students. Practice points are computed on the server and only for a learner, and a repeated `source_event_id` does not award points again.

A student can open and signal only their own proctoring session. Review and event history require `proctoring:review` and, for a teacher or evaluator, an active assignment on that assessment's course. Support agents can read users, the institution, courses, and the audit log. They cannot open proctoring evidence.

Read routes for courses, lessons, assignments, assessments, attendance, results, classes, cohorts, and AI usage require the matching permission and then apply the student, parent, or teaching-assignment filter. Student Success for another learner is limited to a linked parent, an institution-wide academic role, or a teacher of a course that learner is enrolled in. Anyone else gets 404.
