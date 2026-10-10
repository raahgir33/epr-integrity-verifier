import { expect, test } from "@playwright/test";

// T13.8: the fixture API (e2e/fixtures/server.mjs) deliberately has no
// "/processors" (list) route — only "/processors/PWP-05" and its
// sub-paths — so the home page's getProcessors() call 404s, uncaught,
// and must surface via app/error.tsx rather than a blank or half-broken
// page. This is a genuine reachable-service error (HTTP 404), a
// different failure class from e2e/api-down.spec.ts's connection-refused
// case — both must render the same never-blank error state.
test("an uncaught API error surfaces the error boundary, not a blank page", async ({ page }) => {
  const response = await page.goto("/");

  expect(response?.status()).toBe(200); // Next renders the error boundary with a 200, not a 5xx
  await expect(page.getByRole("heading", { name: "Data service unavailable" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
});
