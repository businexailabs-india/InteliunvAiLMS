# AI LMS root-cause analysis

This pass did not rebuild the platform. The React and Vite shell in `src/App.tsx` still routes by component state. The API is the FastAPI app in `services/api`, with PostgreSQL, Alembic, and the existing demo JWT. AI calls go through `get_provider` in `services/api/app/ai/providers.py`. Retrieval is token overlap on `SourceChunk` rows. There is no embedding index.

## BUG-01 and BUG-04 — AI calls

`POST /api/v1/ai/study-buddy` builds a prompt that starts with `Feature=study_buddy prompt_version=1` and then the retrieved chunk text. `MockProvider` used to return that prompt, trimmed to 180 characters, inside a sentence that said it was restating the request. The UI added another `[MOCK AI]` prefix and, separately, painted "Source: Module 3 · Lesson 3.3" on every assistant bubble after the first.

The copilot drawer on Gradebook was a different failure. Its chips and send button had no handler, so they never reached the provider. The gradebook page also reused the attendance explanation, which made the empty score list look like a permissions error.

The mock provider is still the default. A configured OpenAI, Azure OpenAI, or Gemini provider that fails still raises `ProviderError` and is returned as an error. It is not replaced with mock text. This pass did not call a live provider. No API key was added to the browser.

## BUG-03 — answer quality

`retrieve_chunks` ranked institution-scoped chunks by token overlap and then, when nothing overlapped, returned `ranked[:1]`. An unrelated chunk was therefore sent to the model and shown as if it answered the question. The chat UI never read the `citations` array, so the source line could not follow the chunk that was actually retrieved.

The retrieval rule is now: return up to three chunks with overlap greater than zero, otherwise return none. The mock reply quotes that text or says that no approved material matched. It does not invent an AWS explanation. This is a retrieval and prompting defect, not evidence that a live model was wrong. Quality against a paid model was not measured.

## BUG-05 — administrator name

Login and registration already return `display_name` on the session (`src/api/client.ts`). The header ignored it and rendered `roleProfiles["Administrator"]`, which is Olivia Harris. The institution label was already taken from `session.institution_name`. The role code was not changed.

## BUG-02, attendance, and assessments

`.scope-row` expects an icon, a text stack, a badge, and a chevron. Assessment, attendance, and gradebook rows rendered a text stack and a badge only. CSS placed the text in the 32px track. At the default font scale of 1.2 that track wraps a normal title. The assessment "missing fields" in the screenshot are that wrap. Proctored exams still open the checks step before the exam.

## Dashboard

`GET /api/v1/dashboard` counted at most 12 courses and exposed that count as `metrics.courses`. The administrator card labelled it TOTAL LEARNERS. Faculty, engagement, and at-risk were not in the payload; the UI printed 1,248, 87.4%, and 284. The weekly chart, 22 May schedule, and priority alerts are still drawn in the component. They are now marked SAMPLE. The four administrator numbers are enrollment count, teacher or corporate-trainer role count, average attendance, and attendance rows under 75%. `metrics.synthetic` stays true.

## BUG-06 — create screens

`GenericWorkspace` is a catalogue of sample rows. Create called `navigate(module, sub, "New " + sub)` and rendered `GenericActionDetail`, which does not post. Teaching Copilot's six tools all use that workspace. The Question Bank (`LiveQuestionBank` and `POST /api/v1/question-bank`) is the existing persisted authoring path, so Content Generator now opens it. Lesson Planner, Quiz Generator, Rubric Generator, Teaching Insights, and Student Support still have no table.

## BUG-07 — batches

`CorporateCohort` is the batch record. Create is `POST /api/v1/cohorts`. Members are `POST /api/v1/cohorts/{id}/members`, which already refuses a duplicate membership and a user outside the institution. The screen existed as `LiveCompletionReport` and was easy to miss. It is now titled Batches and linked from Administration → Batches and from Student Information. Coordinators were added to the cohort role set. Students are still rejected.

## BUG-08 — reports

Attempts are stored unpublished. Students and parents only receive rows with `published` true. A coordinator, principal, or institution administrator submits `POST /api/v1/scorecards` (`pending_approval`) and then `POST /api/v1/scorecards/{id}/approve`, which sets the scorecard to `published` and publishes attempts for that course. Audit rows are written for the approval. The UI for that flow is `LiveScores`. It was mounted only when the role was Training Coordinator. Administrators and principals can now open it from Assessments → Results and from Reports.

The existing statuses are `pending_approval` and `published`. This pass did not add draft, submitted, and approved as extra columns.

## What was not a defect in the API

Student self check-in remains limited to the caller's own attendance. Staff correction still requires a reason. Unpublished scores stay hidden from students. Those rules were left in place.
