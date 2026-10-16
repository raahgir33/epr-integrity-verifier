"use client";

import { ChevronDown } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { CopyableCurl } from "@/components/apidocs/CopyableCurl";
import type { Endpoint, FieldRow } from "@/lib/apiDocs";

/** The one endpoint that does real work rather than returning a stored
 * result, so its example carries a warning. */
const LIVE_RUN_PATH = "/demo/certificate-batch";

function MethodBadge({ method }: { method: string }) {
  return (
    <span className="rounded-sm border border-border bg-surface-sunk px-1.5 py-0.5 font-mono text-xs font-medium uppercase text-ink">
      {method}
    </span>
  );
}

/** The label is set in small caps for the section rubric, but a schema
 * name is CamelCase and becomes unreadable under a CSS uppercase
 * transform ("DemoCertificateBatchRequest" -> "DEMOCERTIFICATEBATCHREQUEST"),
 * so it is kept in its own case alongside. */
function FieldTable({
  label,
  schemaName,
  rows,
}: {
  label: string;
  schemaName: string | null;
  rows: FieldRow[];
}) {
  if (rows.length === 0) return null;
  const accessibleName = schemaName ? `${label} — ${schemaName}` : label;
  return (
    <div className="overflow-x-auto" role="region" aria-label={accessibleName} tabIndex={0}>
      <table className="w-full border-collapse text-left text-xs">
        <caption className="pb-1.5 text-left text-xs text-ink-muted">
          <span className="font-medium uppercase tracking-wide">{label}</span>
          {schemaName ? (
            <>
              {" — "}
              <code className="font-mono normal-case">{schemaName}</code>
            </>
          ) : null}
        </caption>
        <thead>
          <tr className="border-b border-border">
            <th scope="col" className="py-1.5 pr-3 font-medium text-ink-muted">
              Field
            </th>
            <th scope="col" className="py-1.5 pr-3 font-medium text-ink-muted">
              Type
            </th>
            <th scope="col" className="py-1.5 font-medium text-ink-muted">
              Required
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.name}-${index}`} className="border-b border-border/60 last:border-0">
              <th scope="row" className="py-1.5 pr-3 font-normal text-ink">
                <span style={{ paddingLeft: `${row.depth * 0.9}rem` }} className="font-mono">
                  {row.name}
                </span>
              </th>
              <td className="py-1.5 pr-3 font-mono text-ink-muted">{row.type}</td>
              <td className="py-1.5 text-ink-muted">{row.required ? "yes" : "no"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EndpointSection({ endpoint }: { endpoint: Endpoint }) {
  const isLiveRun = endpoint.path === LIVE_RUN_PATH;
  const [open, setOpen] = useState(false);
  const panelId = useId();

  /** Eighteen endpoints expanded at once is a wall nobody reads, so each
   * starts collapsed. A contents link would then land the reader on a
   * closed card, so a card opens itself when the URL targets it — on
   * first paint and on every later hash change. */
  useEffect(() => {
    function openIfTargeted() {
      if (window.location.hash === `#${endpoint.id}`) setOpen(true);
    }
    openIfTargeted();
    window.addEventListener("hashchange", openIfTargeted);
    return () => window.removeEventListener("hashchange", openIfTargeted);
  }, [endpoint.id]);

  return (
    <section id={endpoint.id} className="card scroll-mt-28">
      <h3>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((isOpen) => !isOpen)}
          className="flex w-full items-start gap-2 rounded-lg p-4 text-left outline-none transition-[color,scale] duration-150 focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary motion-safe:active:scale-[0.99]"
        >
          <ChevronDown
            aria-hidden="true"
            strokeWidth={1.5}
            className={`mt-0.5 size-4 shrink-0 text-ink-muted transition-transform duration-150 ease-out ${open ? "rotate-180" : ""}`}
          />
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-center gap-2">
              <MethodBadge method={endpoint.method} />
              <code className="font-mono text-sm font-medium text-ink">{endpoint.path}</code>
            </span>
            <span className="mt-1 block text-xs font-medium uppercase tracking-wide text-ink-muted">
              {endpoint.summary}
            </span>
          </span>
        </button>
      </h3>

      <div id={panelId} hidden={!open} className="space-y-4 px-4 pb-4">
        <p className="max-w-[80ch] text-pretty text-sm leading-relaxed text-ink-muted">
          {endpoint.description}
        </p>
        {endpoint.params.length > 0 ? (
          <div className="overflow-x-auto" role="region" aria-label="Parameters" tabIndex={0}>
            <table className="w-full border-collapse text-left text-xs">
              <caption className="pb-1.5 text-left text-xs font-medium uppercase tracking-wide text-ink-muted">
                Parameters
              </caption>
              <thead>
                <tr className="border-b border-border">
                  <th scope="col" className="py-1.5 pr-3 font-medium text-ink-muted">
                    Name
                  </th>
                  <th scope="col" className="py-1.5 pr-3 font-medium text-ink-muted">
                    In
                  </th>
                  <th scope="col" className="py-1.5 pr-3 font-medium text-ink-muted">
                    Type
                  </th>
                  <th scope="col" className="py-1.5 font-medium text-ink-muted">
                    Required
                  </th>
                </tr>
              </thead>
              <tbody>
                {endpoint.params.map((param) => (
                  <tr key={param.name} className="border-b border-border/60 last:border-0">
                    <th scope="row" className="py-1.5 pr-3 font-mono font-normal text-ink">
                      {param.name}
                    </th>
                    <td className="py-1.5 pr-3 text-ink-muted">{param.location}</td>
                    <td className="py-1.5 pr-3 font-mono text-ink-muted">{param.type}</td>
                    <td className="py-1.5 text-ink-muted">{param.required ? "yes" : "no"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        <FieldTable
          label="Request body"
          schemaName={endpoint.requestSchemaName}
          rows={endpoint.requestFields}
        />

        {endpoint.streamsBytes ? (
          <p className="text-xs text-ink-muted">
            Responds {endpoint.responseStatus} with the file&rsquo;s own bytes, not JSON.
          </p>
        ) : (
          <FieldTable
            label={`Response ${endpoint.responseStatus}`}
            schemaName={endpoint.responseSchemaName}
            rows={endpoint.responseFields}
          />
        )}

        <CopyableCurl
          command={endpoint.curl}
          warning={
            isLiveRun
              ? "Starts a real verification run. It calls Gemini, counts against the daily cap, and changes what the site shows for that processor."
              : undefined
          }
        />
      </div>
    </section>
  );
}
