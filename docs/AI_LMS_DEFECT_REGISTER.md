# AI LMS defect register

Source: `Testing_AI_LMS25oct26.docx` (eight captions) and the screenshots embedded in that file, traced against the current frontend and API. A cause is listed as confirmed only where the code path matches the screenshot.

| ID | Severity | Summary | Expected | Actual (confirmed) | Root cause | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BUG-01 | High | Study Buddy returns a mock answer that looks like a course explanation | A labelled development answer, or a live-provider answer, grounded in the signed-in user's materials | The bubble started with `[MOCK AI]` and restated the system prompt, including `Feature=study_buddy prompt_version=1` and retrieved chunk text | `MockProvider.generate` copied the first 180 characters of the prompt. The Study Buddy prompt includes the feature header and chunk bodies | `services/api/app/ai/providers.py`, `services/api/app/api/v1/ai.py` | Fixed in code. Covered by `test_mock_reply_does_not_echo_the_system_prompt` |
| BUG-02 | Medium | Assessment Center titles wrap one word per line | Title and description stay readable beside the checks badge | "Module Knowledge Check" and "Proctored · required checks must pass" stacked in a narrow column; the badge stretched | `.scope-row` is a 4-column grid (`32px 1fr auto 18px`). The exam button has two children, so the title landed in the 32px column | `src/index.css`, `src/live/ExamSession.tsx` | Fixed with `.scope-row.record`. Not browser-verified this pass |
| BUG-03 | High | Study Buddy cites the wrong lesson and answers off-topic questions from an unrelated chunk | Cite only overlapping authorized material. If none matches, say so | Every AI bubble showed "Source: Module 3 · Lesson 3.3". The context panel was Mathematics Grade 10. Retrieval returned the first chunk even when token overlap was zero | UI ignored `citations` from the API. `retrieve_chunks` ended with `or ranked[:1]` | `src/App.tsx` Study Buddy, `services/api/app/api/v1/ai.py` | Fixed. Empty retrieval is covered by `test_mock_reply_without_materials_does_not_invent_a_source`. There is still no embedding or vector store |
| BUG-04 | High | Gradebook looks unfinished and the copilot does not answer | Gradebook describes published scores. Copilot sends a real request | Gradebook reused the attendance sentence "You can confirm attendance only for yourself." Copilot prompt chips had no click handler. The drawer did not call the API | `LivePersonalRecord` used one `copy` string for Attendance and Gradebook. Copilot buttons were static | `src/live/LiveAdmin.tsx`, `src/App.tsx` copilot drawer | Copy and copilot request are fixed. Copilot uses `POST /api/v1/ai/study-buddy` and labels mock replies. No browser pass |
| BUG-05 | High | After creating an administrator, the header shows Olivia Harris | Header shows the signed-in user's `display_name` | `profile` was `roleProfiles[role]`. Administrator is hardcoded as Olivia Harris / OH. Greeting was "Good morning, Olivia" | `src/App.tsx` `roleProfiles` and `const profile=roleProfiles[role]` | Confirmed in `src/App.tsx` and `src/api/client.ts` (`Session.display_name`) | Fixed for a live session. Prototype role switch, which clears the session, still uses the persona card. Role is not rewritten |
| BUG-06 | High | Teaching Copilot "Create" does not save Content Generator, Lesson Planner, Quiz Generator, Rubric Generator, Teaching Insights, or Student Support | Create persists a real record and the list reloads | Those screens are `GenericWorkspace`: KPIs and rows are literals, and Create only opened a sample detail | No content-draft table backs those six screens | `src/App.tsx` `GenericWorkspace`, `moduleDetails` | Fixed. Content Generator opens the Question Bank. Lesson Planner, Quiz Generator, Rubric Generator, Teaching Insights, and Student Support save `teaching_notes` rows and reload them. Class Analytics remains a sample workspace |
| BUG-07 | High | No obvious place to add a batch | Create a batch, list it, and add students, using the existing cohort model | Cohort create already existed at `POST /api/v1/cohorts` and was rendered only inside Analytics for an administrator, titled as a completion report. Coordinators could not call the member API | UI route and `CORPORATE_ROLES` omitted `coordinator` | `src/live/LiveAdmin.tsx` `LiveCompletionReport`, `services/api/app/api/v1/lms.py`, `services/api/app/api/v1/training.py` | Fixed. Administration → Batches, and Student Information for an administrator or coordinator, show the existing cohort screen. No second batch model |
| BUG-08 | High | Student reports have no visible create / update / publish path | Coordinator or administrator enters scores, submits a scorecard, and publishes. Students see published results only | Student gradebook correctly hid unpublished attempts, but the publish screen was only mounted for Training Coordinator on Assessments | `GET /api/v1/results` filters `published` for students and parents. `POST /api/v1/scorecards` then `POST /api/v1/scorecards/{id}/approve` sets attempts `published=True` | `services/api/app/api/v1/lms.py`, `src/live/LiveAcademics.tsx` `LiveScores` | Navigation added: Assessments → Results for an administrator or principal, and Reports for administrator, coordinator, and principal. Existing statuses are `pending_approval` and `published`. A separate draft/submitted/approved machine was not added |
| DASH-01 | High | Administrator dashboard shows production-looking numbers | Totals match institution records, and sample charts are labelled | TOTAL LEARNERS used `metrics.courses`. Faculty 1,248, engagement 87.4%, and at-risk 284 were literals. The chart, 22 May schedule, and priority alerts were also literals | `src/App.tsx` Dashboard; `GET /api/v1/dashboard` previously returned only course count, attendance average, roles, and `synthetic: true` | Confirmed in both files | KPI row, lesson-completion chart, class schedule, alerts, and coordinator batch list now come from `GET /api/v1/dashboard`. Empty sections say there is no record. `metrics.synthetic` remains true because seeded tenants are synthetic |
| ATTEND-01 | Medium | Attendance course titles are unreadable | Course name and session count stay on one readable row | Same two-child `.scope-row` as BUG-02 | `src/live/LiveAdmin.tsx` attendance rows | Fixed with `.scope-row.record`. Self check-in versus staff correction was not changed |
| ASSESS-01 | Low | Assessment rows look like missing module fields | Required checks still block a proctored exam, and the title is readable | The "incomplete" look was the 32px column, not missing question data | `src/live/ExamSession.tsx` | Layout fixed. Camera, microphone, and identity checks are unchanged |

## Reproduction notes

1. Sign in and open AI Study Buddy. Ask a question that is not in the enrolled course. Before the fix the reply echoed the prompt and cited Module 3 Lesson 3.3.
2. Open Assessments as a student. The knowledge-check title wrapped vertically beside CHECKS REQUIRED.
3. Open Attendance. Course titles wrapped the same way.
4. Open Gradebook as a student. The page used the attendance sentence, and the copilot chips did nothing.
5. Register an administrator and sign in. The header showed Olivia Harris.
6. Open Teaching Copilot → Content Generator and use Create. Nothing was stored.
7. Look for a batch list. The working form was buried under Analytics.
8. Open Gradebook as a student with no approved scorecard. Published results stay empty until Assessments → Results or Reports is used to approve a scorecard.

## Tests that cover these defects

Executed in `services/api` with `python -m pytest tests --tb=no -ra`: **95 passed, 15 skipped, 0 failed**.

Directly relevant new or updated tests:

- `test_mock_reply_does_not_echo_the_system_prompt`
- `test_mock_reply_without_materials_does_not_invent_a_source`
- `test_timeout_maps_to_provider_error`
- `test_coordinators_can_manage_batches`
- `test_students_cannot_manage_batches`
- `test_every_api_route_requires_authentication` now also posts to study-buddy, cohorts, and scorecards without a token and expects 401 or 403

Existing adapter tests still cover a successful provider parse, retries, provider failure, malformed JSON, and an empty provider answer.
