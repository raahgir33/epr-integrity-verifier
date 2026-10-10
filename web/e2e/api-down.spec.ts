import { expect, test } from "@playwright/test";
import { API_DOWN_APP_PORT } from "../playwright.config";

// T13.8: a dedicated second Next instance (playwright.config.ts) whose
// API_BASE_URL points at a port nothing listens on — a real connection-
// refused failure, not a mocked one. This must still render the same
// never-blank error state as e2e/error-boundary.spec.ts's reachable-but-
// erroring case, not a blank page or an unhandled exception. Request
// interception can't simulate this: the failure happens during server-
// side rendering, before any request reaches the browser.
test("the API being completely unreachable never shows a blank page", async ({ page }) => {
  const response = await page.goto(`http://localhost:${API_DOWN_APP_PORT}/`);

  expect(response?.status()).toBe(200);
  await expect(page.getByRole("heading", { name: "Data service unavailable" })).toBeVisible();
  await expect(
    page.getByText("The verification API could not be reached.", { exact: false })
  ).toBeVisible();
});
