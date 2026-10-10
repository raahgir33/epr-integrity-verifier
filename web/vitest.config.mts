import { defineConfig } from "vitest/config";

// e2e/ holds Playwright specs (web/playwright.config.ts, `npm run
// test:e2e`) — excluded here so vitest's default *.spec.ts glob doesn't
// also try to run them as unit tests.
export default defineConfig({
  test: {
    exclude: ["**/node_modules/**", "**/dist/**", "e2e/**"],
  },
});
