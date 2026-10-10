import type { NextConfig } from "next";

// T13.8: no nonces (see node_modules/next/dist/docs/01-app/02-guides/
// content-security-policy.md's "Without Nonces" section) — every page
// here is already statically-optimizable where possible, and this app
// has no third-party scripts/styles to allowlist. style-src needs
// 'unsafe-inline' for Next's own injected critical CSS/font `<style>`
// tags (next/font self-hosts, so no external font-src is needed at all).
// Everything else — scripts, images, API calls — is same-origin: every
// client fetch in components/ goes through this app's own /api/* route
// handlers, never straight to a different origin (the internal engineering
// notes' Next.js conventions).
// Dev-only: React Refresh reconstructs component stacks with eval() in
// `next dev` (never in a production build — React's own eval() use is
// dev-only, per React's error message). script-src without 'unsafe-eval'
// blocks that and breaks the dev overlay, so it's added only when
// NODE_ENV !== "production" — the deployed Cloud Run image always builds
// with `next build`, so this never reaches production traffic.
const isDev = process.env.NODE_ENV !== "production";

const cspHeader = [
  "default-src 'self'",
  // 'unsafe-inline' here isn't optional without a nonce (which forces
  // every page to render dynamically — too big a change for this task):
  // Next and next-themes both inject real inline <script> tags (the
  // no-flash theme script, hydration data) that a stricter policy blocks
  // outright — confirmed by actually loading the page: without this,
  // React hydration failed completely (console showed CSP violations on
  // every inline script plus React error #412), silently breaking the
  // whole app rather than "just" fonts/images.
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const nextConfig: NextConfig = {
  output: "standalone",
  // T13.8: only set for e2e/api-down.spec.ts's dedicated second `next
  // dev` instance — this Next version refuses to run two dev servers
  // against the same .next directory at once ("Another next dev server
  // is already running"), so that instance gets its own distDir instead.
  // Unset (default ".next") for every normal run.
  ...(process.env.NEXT_DIST_DIR ? { distDir: process.env.NEXT_DIST_DIR } : {}),
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Content-Security-Policy", value: cspHeader },
        ],
      },
    ];
  },
};

export default nextConfig;
