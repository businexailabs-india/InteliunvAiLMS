# AI LMS fix summary

No migration was added. No provider secret was written into the frontend. The live site was not redeployed in this pass.

## Changed behaviour

- Mock Study Buddy answers no longer repeat the system prompt. If retrieval finds overlapping course text, the mock answer quotes it. If it finds none, the answer says it is not sourced.
- Retrieval no longer falls back to an unrelated chunk.
- Study Buddy shows API citation titles, or an explicit "no course source" line. The Mathematics Grade 10 panel is labelled as a sample.
- The signed-in header and greeting use `session.display_name` when a live session exists.
- Administrator KPIs, the 7-day lesson chart, the class list, alerts, and the coordinator batch list use `GET /api/v1/dashboard`. Empty panels say there is no record.
- Teaching Copilot lesson plans, quizzes, rubrics, insights, and support notes are stored in `teaching_notes`. Content Generator still opens the Question Bank.
- Assessment, attendance, and published-result rows use `.scope-row.record` so titles are not forced into a 32px column.
- Gradebook copy no longer says the user can confirm attendance.
- The copilot drawer calls `POST /api/v1/ai/study-buddy` and shows the error text when the call fails.
- Batches are the existing cohort screen, opened from Administration → Batches and from Student Information for an administrator or coordinator. Coordinators may create cohorts and add members. Students may not.
- Scorecard review is `LiveScores`, opened from Assessments → Results (administrator or principal) and from Reports (administrator, coordinator, or principal). Students still only see published attempts.
- Teaching Copilot sample tables are labelled as unsaved. Create on those screens opens the Question Bank.

## Files

- `src/App.tsx`
- `src/index.css`
- `src/live/ExamSession.tsx`
- `src/live/LiveAdmin.tsx`
- `services/api/app/ai/providers.py`
- `services/api/app/api/v1/ai.py`
- `services/api/app/api/v1/lms.py`
- `services/api/app/api/v1/training.py`
- `services/api/tests/test_ai_providers.py`
- `services/api/tests/test_ai_adapters.py`
- `services/api/tests/test_health.py`
- `services/api/tests/test_rbac.py`

## Left unchanged on purpose

- Proctored assessments still require the existing checks before the exam starts.
- Students still cannot publish scorecards or edit someone else's attendance.
- Mock mode stays the default until `BUSINEX_AI_PROVIDER` and a credential are set. Real provider failures stay errors.
- Generic Teaching Copilot tools other than the Question Bank redirect do not pretend to save.

## Environment

Docker Desktop was not running (`npipe:////./pipe/dockerDesktopLinuxEngine` missing), so the web container was not rebuilt and the UI was not opened. Browser tools were not available. Start Docker and hard-refresh after the next deploy before judging the layout on the public site.
