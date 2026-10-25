# IntelUniVen AI Edu Lab

React + Vite frontend and a FastAPI / PostgreSQL backend for a multi-tenant learning platform.
Seeded data in this repository is synthetic.

```
src/                    React app (App.tsx shell, src/live/* screens wired to the API)
services/api/           FastAPI modular monolith, Alembic migrations, pytest suites
IntelUniVen_Backend_Starter/synthetic-data/   synthetic catalog, users, and assessments
infra/containers/       Docker Compose (postgres, redis, keycloak, api, worker, web)
scripts/                verify_integration.py, smoke_web.py
docs/                   architecture, gap analysis, roadmap, integration status
```

## Run locally

```powershell
docker compose -f infra/containers/compose.yaml up -d
docker exec containers-api-1 python -m app.import_seed --root /data/synthetic
```

- Web: http://localhost:8443
- API docs: http://localhost:8000/docs
- Keycloak: http://localhost:8080
- Environment reference: `services/api/config.example.env`
- Demo password: `Demo@2025`
- Seeded accounts, all `@inteluniven.edu`: `aarav.sharma` (student), `maya.chen` (teacher), `riya.nair` (coordinator), `priya.sharma` (parent), `david.wilson` (principal), `olivia.harris` (admin)

New accounts created from the signup screen use their own password hash. The login identifier is the email address.

## Published site

The static production build is served at https://ailms-app.34.180.38.27.sslip.io.
After a deploy, hard-refresh the browser so it loads the new asset hash.

## Verify

```powershell
python -m pytest services/api/tests --ignore=services/api/tests/test_live_stack.py
python scripts/verify_integration.py
python scripts/smoke_web.py
```

`test_live_stack.py` runs only when the API is reachable at `http://localhost:8000`.

## Change request register

Keep this table current when a CR is implemented, narrowed, or reverted. Status values:

- **Done** — the accepted flow works from the signed-in UI through the API and the database.
- **Partial** — a real slice works, and the remaining gap is listed in the notes.
- **Open** — not built.

| CR | Title | Status | What shipped |
| --- | --- | --- | --- |
| CR-01 | User registration | Done | Signup posts to `POST /api/v1/auth/register`. Passwords are stored as salted `pbkdf2_sha256` hashes. Duplicate email returns 409. Password rule: 8+ characters, one digit, one uppercase letter. Northstar, Meridian, and Horizon join the existing demo tenants. |
| CR-02 | Authentication | Done | `POST /api/v1/auth/demo-login` checks the stored hash when one exists, otherwise the demo password. The API issues a 12-hour demo JWT. The UI maps backend role codes onto Student, Teacher, Coordinator, Parent, Principal, and Administrator dashboards. Wrong password and unknown email return 401. Protected routes reject a missing or invalid token. |
| CR-03 | Course and lesson mapping | Done | Course cards open `cid:<course id>`. Continue opens the first incomplete lesson in that course. The lesson progress bar uses completed lessons divided by the course lesson count. `POST /api/v1/progress` records completion on `lesson_progress` for the opened lesson id. |
| CR-04 | Dynamic learning paths | Done | `GET /api/v1/learning-paths` returns the selected course's lessons, this user's completion, and a lock until the previous lesson is complete. Progress percent is completed lessons divided by the course lesson count. With no enrolled course, the screen says no path is assigned. |
| CR-05 | Assignments | Done | Teachers and administrators publish an assignment with instructions, max score, and due date on `POST /api/v1/assignments`. Enrolled students submit text or a text file. A second submit updates the same row and `submitted_at`. Score and feedback come from `POST /api/v1/submissions/{id}/grade`. An empty submission returns 422. A due date in the past returns 409. |
| CR-06 | Assessment integrity checks | Done | Each assessment stores camera, microphone, and identity as `required`, `optional`, or `off`. A proctored assessment with an empty rule set requires all three. Identity passes only when the typed name matches the signed-in account. Camera and microphone require a device label from the browser check. `POST /api/v1/proctoring/sessions` returns 403 when a required check fails, and the attempt stays blocked until a `checks_passed` session exists. |
| CR-07 | Virtual classroom scheduling | Done | Teachers, coordinators, and administrators create a class with `POST /api/v1/classes` (title, course, start, duration, timezone). Students receive 403 on that endpoint and do not see the schedule form. Enrolled students see the class on Live Classes. A host or coordinator can remove a class. Another teacher cannot change a class they do not host. |
| CR-08 | Study and revision sessions | Done | Students save a personal session with `POST /api/v1/study-sessions`. Title, start time, and IANA timezone are required. The list reloads from the account, so it remains after refresh. Update and delete apply only to the owner. |
| CR-09 | Attendance | Done | Students confirm only their own attendance with `POST /api/v1/attendance/check-in` for an enrolled course. `GET /api/v1/attendance` returns that student's rows. `POST /api/v1/attendance/record` is limited to teachers and coordinators, so a student cannot write the class register. |
| CR-10 | Quiz Challenge | Done | Teachers and students play the course deck from `GET /api/v1/practice-deck?game=quiz`. The deck is that course's approved bank, or its multiple-choice assessment questions. Answers are omitted. `POST /api/v1/practice-deck/submit` grades on the server. `POST /api/v1/gamification/play` rejects a client-supplied score. Repeating the same `source_event_id` awards no extra points. |
| CR-11 | Quick Quest | Done | Quick Quest uses the same saved session flow with `game=quick_quest`, a 15-second timer per question, server scoring, feedback, points, and the accuracy badge. Recent results come back from `GET /api/v1/gamification`. |

### Current behavior

- CR-03 Continue opens the first lesson whose earlier lessons are complete. The lesson progress bar uses that same completion count. Saved completion still lives on `lesson_progress`.
- CR-05 accepts a text-file attachment. A later submit updates the same submission row and refreshes `submitted_at`.
- CR-06 identity is accepted only when the typed name matches the signed-in account. Camera and microphone require a browser device check and a device label. A required check that fails returns 403 and does not open the assessment.
- CR-10 and CR-11 use that course's approved question bank, or that course's multiple-choice assessment questions, when either exists. A course with neither returns an empty deck. The built-in decks are used only when no course is selected. Teachers and students both open the scored Quiz Challenge.
- Seeded formal assessments are four multiple-choice questions. Quiz Challenge, Quick Quest, and any assessment created with several questions use the same multi-question flow.
- `POST /api/v1/gamification/play` rejects a client-supplied correct count. Quiz Challenge and Quick Quest score answers on `POST /api/v1/practice-deck/submit`.

## Schema added for these CRs

| Migration | Change |
| --- | --- |
| `0004_user_password` | `users.password_hash` for CR-01 and CR-02 |
| `0005_assignments_integrity` | `assignments.due_at`, `assessments.integrity`, `points_ledger.created_at` for CR-05, CR-06, CR-10, and CR-11 |
| `0006_classes_and_study` | `scheduled_classes` and `study_sessions` for CR-07 and CR-08 |
| `0007_submission_files` | `submissions.submitted_at`, `attachment_name`, and `attachment_text`. Single-question seeded assessments become four multiple-choice questions. |

## Main files

| Area | Files |
| --- | --- |
| Registration and login | `services/api/app/api/v1/auth.py`, `services/api/app/passwords.py`, `src/api/client.ts`, signup and login screens in `src/App.tsx` |
| Courses, lessons, progress | `services/api/app/api/v1/lms.py`, course and lesson screens in `src/App.tsx` |
| Learning path | `services/api/app/api/v1/lms.py`, `services/api/app/services/learning_path.py`, `LearningPathWorkspace` in `src/App.tsx` |
| Classroom and study session | `services/api/app/api/v1/academics.py`, `src/live/Schedule.tsx`, `VirtualClassroomWorkspace` in `src/App.tsx` |
| Assignments | `services/api/app/api/v1/lms.py`, `services/api/app/api/v1/academics.py`, `src/live/LiveAcademics.tsx` |
| Assessment checks | `services/api/app/services/integrity.py`, `services/api/app/api/v1/engagement.py`, `services/api/app/api/v1/lms.py`, `src/live/ExamSession.tsx` |
| Attendance | `services/api/app/api/v1/academics.py`, `services/api/app/api/v1/lms.py`, `src/live/LiveAdmin.tsx` |
| Quiz and Quick Quest | `services/api/app/api/v1/engagement.py`, `services/api/app/services/grading.py`, `src/live/PracticeGame.tsx` |
| Rule tests | `services/api/tests/test_cr_rules.py`, `services/api/tests/test_grading.py`, `services/api/tests/test_passwords.py`, `services/api/tests/test_rbac.py` |

## Other product changes

- Font size control on the login screen, signup screen, and top bar. The scale is `sm` 1, `md` 1.2, `lg` 1.4 through the CSS variable `--text-scale`, saved in `localStorage` as `inteluniven-font-scale`.
- Signed-in course navigation uses the course id. Sample catalog cards remain available when the API catalog is empty.
- Student attendance list applies the student filter after the visibility check, so a learner does not receive the class-wide register.

## Principles

- Tenant isolation is enforced by PostgreSQL forced row-level security, together with API checks.
- Grades, attendance, and assessment integrity changes write an audit event.
- Proctoring records the required checks and the attempt. A failed required check stops entry. The record is an integrity gate, and the product does not run facial recognition.
- AI responses are mocked unless a provider key is configured, and mock replies are labelled.

## Updating this register

When a CR changes, edit the status, the shipped behavior, and the notes in this file in the same change as the code. Add a migration row when the database shape changes.
