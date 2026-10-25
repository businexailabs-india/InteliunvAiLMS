import { defineConfig } from "@playwright/test";

// Runs against the already-running stack (docker compose up): web on 8443, API behind its proxy.
// Uses the system Microsoft Edge so no browser download is needed. Override with E2E_CHANNEL=chrome
// or E2E_CHANNEL= (empty) to use Playwright's bundled Chromium after `npx playwright install chromium`.
const channel = process.env.E2E_CHANNEL === undefined ? "msedge" : process.env.E2E_CHANNEL || undefined;

export default defineConfig({
  testDir: "./tests",
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "report" }]],
  outputDir: "results",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8443",
    channel,
    headless: true,
    viewport: { width: 1440, height: 900 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});
