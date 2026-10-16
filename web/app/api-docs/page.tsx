import type { Metadata } from "next";
import { connection } from "next/server";
import { EndpointSection } from "@/components/apidocs/EndpointSection";
import { Heading } from "@/components/ui/Heading";
import { listEndpoints } from "@/lib/apiDocs";

export const metadata: Metadata = {
  title: "API Documentation",
  description: "Every public endpoint of the verification API, with parameters, schemas and a runnable example.",
};

/** The API's base URL is read server-side at request time, the same way
 * every other page reads it — never baked in at build time, which would
 * pin the examples to whichever service the image happened to be built
 * against. The endpoint list itself comes from the committed schema, so
 * the page is identical in every environment except these URLs.
 *
 * Unlike every other page here, this one has no data fetch to make it
 * dynamic on its own, so it prerendered at build time and captured the
 * build machine's API_BASE_URL. `connection()` stops prerendering and
 * defers the render to a real request. (`export const dynamic` would do
 * it today but is removed once Cache Components is enabled; this is the
 * API that survives that.) */
export default async function ApiDocsPage() {
  await connection();
  const baseUrl = process.env.API_BASE_URL ?? "";
  const displayBase = baseUrl || "https://<api-url>";
  const endpoints = listEndpoints(displayBase);

  return (
    <div className="space-y-8">
      <div className="text-center">
        <Heading>API Documentation</Heading>
        <p className="mx-auto mt-1 max-w-[70ch] text-pretty text-sm leading-loose tracking-wide text-ink-muted">
          Every Public Endpoint of the Verification API. Responses Are Served From Precomputed
          Results, So Each One Returns the Same Figures the Site Shows.
        </p>
        {baseUrl ? (
          <p className="mx-auto mt-2 max-w-[70ch] text-sm text-ink-muted">
            Base URL <code className="font-mono text-ink">{baseUrl}</code>
          </p>
        ) : null}
        <p className="mx-auto mt-1 max-w-[70ch] text-xs text-ink-muted">
          This page never calls the API. Each example is for copying and running yourself.
        </p>
      </div>

      <nav aria-label="Endpoints" className="card p-4">
        <h2 className="text-xs font-medium uppercase tracking-wide text-ink-muted">
          {endpoints.length} Endpoints
        </h2>
        <ul className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2 lg:grid-cols-3">
          {endpoints.map((endpoint) => (
            <li key={endpoint.id} className="text-xs">
              <a
                href={`#${endpoint.id}`}
                className="inline-flex min-h-10 items-center gap-1.5 rounded-sm font-mono text-ink-muted underline decoration-dotted underline-offset-2 outline-none transition-colors duration-150 hover:text-ink focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              >
                <span className="uppercase">{endpoint.method}</span> {endpoint.path}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <div className="space-y-4">
        {endpoints.map((endpoint) => (
          <EndpointSection key={endpoint.id} endpoint={endpoint} />
        ))}
      </div>

      <p className="mx-auto max-w-[80ch] text-pretty text-center text-xs leading-relaxed text-ink-muted">
        This reference is generated from the service&rsquo;s own OpenAPI schema, so it lists exactly
        what the API publishes. Operational endpoints used only for deployment are not part of the
        public surface and do not appear here.
      </p>
    </div>
  );
}
