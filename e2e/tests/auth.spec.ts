import { expect, test } from "@playwright/test";
import { login, probe, signedIn } from "./helpers";

test("wrong password is rejected and no session is created", async ({ page }) => {
  probe(page);
  await login(page, "aarav.sharma@inteluniven.edu", "not-the-password");
  await expect(page.locator(".signup-error")).toBeVisible();
  await expect(page.locator(".sidebar .nav-scroll")).toHaveCount(0);
});

test("unknown user is rejected", async ({ page }) => {
  probe(page);
  await login(page, "nobody@inteluniven.edu");
  await expect(page.locator(".signup-error")).toBeVisible();
  await expect(page.locator(".sidebar .nav-scroll")).toHaveCount(0);
});

test("API calls without a token are refused", async ({ request }) => {
  const res = await request.get("/api/v1/auth/me");
  expect(res.status()).toBe(401);
});

test("a signed-in session survives a page reload", async ({ page }) => {
  probe(page);
  await login(page, "maya.chen@inteluniven.edu");
  await signedIn(page);
  await page.reload();
  await signedIn(page);
});
