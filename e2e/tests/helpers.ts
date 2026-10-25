import { expect, type Page } from "@playwright/test";

export const PASSWORD = "Demo@2025";

export interface Probe {
  /** Uncaught page exceptions. */
  errors: string[];
  /** API responses with status >= 400, as "STATUS METHOD path". */
  apiFailures: string[];
}

/** Starts collecting page errors and failing API calls. Call before navigating. */
export function probe(page: Page): Probe {
  const result: Probe = { errors: [], apiFailures: [] };
  page.on("pageerror", (err) => result.errors.push(err.message));
  page.on("response", (res) => {
    const url = new URL(res.url());
    if (url.pathname.startsWith("/api/") && res.status() >= 400) {
      result.apiFailures.push(`${res.status()} ${res.request().method()} ${url.pathname}`);
    }
  });
  return result;
}

export async function login(page: Page, email: string, password = PASSWORD): Promise<void> {
  await page.goto("/");
  await page.getByPlaceholder("name@institution.edu").first().fill(email);
  await page.getByPlaceholder("Enter password").fill(password);
  await page.getByRole("button", { name: /Sign in securely/ }).click();
}

export async function signedIn(page: Page): Promise<void> {
  await expect(page.locator(".sidebar .nav-scroll")).toBeVisible();
}

/** Titles of every module button in the sidebar. */
export async function sidebarModules(page: Page): Promise<string[]> {
  await signedIn(page);
  return page.locator(".sidebar .nav-scroll button").evaluateAll((els) => els.map((el) => el.getAttribute("title") ?? ""));
}

export async function openModule(page: Page, name: string, sub?: string): Promise<void> {
  await page.locator(`.sidebar .nav-scroll button[title="${name}"]`).click();
  if (sub) {
    await page.locator(".main-content").getByRole("button", { name: sub, exact: true }).first().click();
  }
}

/**
 * Waits for a live screen: its heading is shown, the loading card is gone and no load error is
 * displayed. Anything the API rejected would otherwise hide behind a half-rendered page.
 */
export async function expectLiveScreen(page: Page, heading: string): Promise<void> {
  await expect(page.locator(".main-content h1").first()).toHaveText(heading);
  await expect(page.getByText(/^Loading .* from the API/)).toHaveCount(0);
  await expect(page.getByRole("alert").filter({ hasText: "Could not load this data" })).toHaveCount(0);
}
