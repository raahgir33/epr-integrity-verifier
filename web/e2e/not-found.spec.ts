import { expect, test } from "@playwright/test";

// T13.8: a friendly not-found.tsx must render for any unknown route,
// never a blank page or the framework's default 404.
test("an unknown route renders the friendly not-found page", async ({ page }) => {
  const response = await page.goto("/this-route-does-not-exist");

  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "Not found" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Back to Overview" })).toBeVisible();
});
