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

// T16b: the landing page needs routes the default fixture deliberately
// withholds — e2e/error-boundary.spec.ts depends on "/processors" 404ing
// so the home page's getProcessors() surfaces the error boundary. Rather
// than weaken that, the same fixture file runs a second time in
// FIXTURE_MODE=landing (full landing data + the stateful live-run
// simulation) on its own port, with its own Next instance pointed at it.
const LANDING_FIXTURE_PORT = 4102;
const LANDING_APP_PORT = 4202;

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
      command: `node e2e/fixtures/server.mjs`,
      env: { FIXTURE_PORT: String(LANDING_FIXTURE_PORT), FIXTURE_MODE: "landing" },
      port: LANDING_FIXTURE_PORT,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: `npx next dev -p ${LANDING_APP_PORT}`,
      env: {
        API_BASE_URL: `http://localhost:${LANDING_FIXTURE_PORT}`,
        // Own distDir, same reason as the api-down instance below.
        NEXT_DIST_DIR: ".next-landing",
      },
      port: LANDING_APP_PORT,
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

export { API_DOWN_APP_PORT, LANDING_APP_PORT };
