import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    // T16b: the e2e dev-server instances get their own distDirs
    // (.next-api-down, .next-landing -- Next refuses two dev servers
    // sharing one .next/). Generated output, not source.
    ".next-*/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Vendored Magic UI source (T13.5b plan) — kept unmodified aside from a
    // license header, so it isn't held to this project's own lint rules.
    "components/magicui/**",
  ]),
]);

export default eslintConfig;
