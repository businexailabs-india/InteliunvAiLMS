# AI LMS test results

Command, from `services/api`:

```text
python -m pytest tests --tb=no -ra
```

Result, executed in this pass: **95 passed, 15 skipped, 0 failed** (8.00s). Exit code 0.

A second run with `python -m pytest tests -q --tb=line` also exited 0. Its progress line showed no failures. The short summary above is the count used for this report.

## Skips

| Count | Reason |
| --- | --- |
| 3 | `tests/test_live_stack.py` — API not reachable at `http://localhost:8000` |
| 12 | `tests/test_rls.py` — database unavailable (`InvalidPasswordError`) |

Those skips are environment gaps. They are not counted as passes.

## Cases that ran and passed

| Area | Tests |
| --- | --- |
| Mock answer does not echo `Feature=study_buddy` or `prompt_version` | `test_mock_reply_does_not_echo_the_system_prompt` |
| Mock answer with no retrieved material does not invent a source | `test_mock_reply_without_materials_does_not_invent_a_source` |
| Mock provider stays labelled | `test_mock_provider_is_clearly_labelled` |
| Provider success, retry, HTTP failure, timeout, malformed JSON, empty body | `tests/test_ai_adapters.py`, including `test_timeout_maps_to_provider_error` |
| Unauthenticated study-buddy, cohort, and scorecard posts | `test_every_api_route_requires_authentication` expects 401 or 403 |
| Coordinator may manage batches; student may not | `test_coordinators_can_manage_batches`, `test_students_cannot_manage_batches` |

## Not executed

- Frontend lint, TypeScript check, and Vite build. This workspace has no `node_modules`, and Docker was not running, so the web image was not used.
- Playwright in `e2e/`.
- A live-provider smoke test. No provider credential was used.
- Browser walkthrough of login, batch create, enrollment, assessment, attendance, score entry, and report publication.
- Tenant-isolation tests that need PostgreSQL. The RLS file skipped as above.

A defect that depends on the screen (layout, header name, navigation) is fixed in source and is not yet demonstrated in a browser.
