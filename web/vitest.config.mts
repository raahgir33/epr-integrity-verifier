import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// e2e/ holds Playwright specs (web/playwright.config.ts, `npm run
// test:e2e`) — excluded here so vitest's default *.spec.ts glob doesn't
// also try to run them as unit tests.
export default defineConfig({
  resolve: {
    // Mirrors tsconfig.json's "@/*": ["./*"] — needed as of T13.6's
    // lib/landing.test.ts, the first vitest spec to import a module that
    // itself imports via the "@/" alias (lib/landing.ts -> "@/lib/api").
    // Vite doesn't read tsconfig paths on its own; no new dependency
    // (vite-tsconfig-paths) needed for one alias.
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
  test: {
    exclude: ["**/node_modules/**", "**/dist/**", "e2e/**"],
  },
});
