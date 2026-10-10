import { defineConfig } from "@playwright/test";

const FIXTURE_PORT = 4100;
const APP_PORT = 4200;

// T13.8: a second Next instance pointed at a port nothing listens on, so
// e2e/api-down.spec.ts can exercise a real connection-refused failure
// (distinct from the fixture-backed project's 404-shaped app errors) —
// see that spec for why a second app server, not request interception,
// is necessary here (the failure happens during server-side rendering,
// before anything reaches the browser).
const API_DOWN_APP_PORT = 4201;
const UNREACHABLE_PORT = 4199;

/** Committed e2e config (round 7 fix). Starts the plain-Node fixture API
 * (e2e/fixtures/server.mjs — no GCP/Gemini, no real api/ service) and the
 * Next.js dev server pointed at it via API_BASE_URL, then runs the specs
 * in e2e/ against that pair. Dev mode, not a production build, so the
 * suite stays fast to run locally and in review; the project's existing
 * manual build+start screenshot pass (outside this repo) remains the
 * production-fidelity check before a release. */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  use: {
    baseURL: `http://localhost:${APP_PORT}`,
  },
  webServer: [
    {
      command: `node e2e/fixtures/server.mjs`,
      env: { FIXTURE_PORT: String(FIXTURE_PORT) },
      port: FIXTURE_PORT,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: `npx next dev -p ${APP_PORT}`,
      env: { API_BASE_URL: `http://localhost:${FIXTURE_PORT}` },
      port: APP_PORT,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: `npx next dev -p ${API_DOWN_APP_PORT}`,
      env: {
        API_BASE_URL: `http://localhost:${UNREACHABLE_PORT}`,
        // Separate distDir: this Next version refuses a second `next
        // dev` against the same .next directory ("Another next dev
        // server is already running") — see next.config.ts.
        NEXT_DIST_DIR: ".next-api-down",
      },
      port: API_DOWN_APP_PORT,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});

export { API_DOWN_APP_PORT };
