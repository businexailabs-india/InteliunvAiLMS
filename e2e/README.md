# Browser tests (Playwright)

Drive the real UI in a real browser against the running stack. They sign in as each demo persona,
check the sidebar against `src/access.ts`, open every API-backed screen and fail on uncaught page
errors, any `/api` response >= 400, a stuck loading card or a "Could not load this data" banner.

```powershell
docker compose -f infra/containers/compose.yaml up -d   # web on 8443, API behind its proxy
cd e2e
npm install
npx playwright test                 # uses system Microsoft Edge
npx playwright show-report report   # HTML report
```

- `E2E_CHANNEL=chrome` uses Chrome. `E2E_CHANNEL=` (empty) uses bundled Chromium after
  `npx playwright install chromium`.
- `E2E_BASE_URL` points at a different web URL.
- The suite is read-only: it creates, edits and deletes no data, so it is safe to rerun.

What it does not cover: write flows (grading, attendance edits, approvals; the API scenario script
covers those), Keycloak redirect login (not built in the UI), and visual regressions.
