"use client";

import { useState } from "react";
import { EvidenceList } from "@/components/EvidenceLink";
import type { ReasoningStepOut } from "@/lib/api";

function ToolArgs({ args }: { args: Record<string, unknown> | null }) {
  if (!args || Object.keys(args).length === 0) return null;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {Object.entries(args).map(([key, value]) => (
        <span key={key} className="rounded bg-surface-sunk px-1.5 py-0.5 font-mono text-xs text-ink-muted">
          {key}: {Array.isArray(value) ? value.join(", ") : String(value)}
        </span>
      ))}
    </span>
  );
}

export function ToolStep({
  step,
  knownDocIds,
}: {
  step: ReasoningStepOut;
  knownDocIds: ReadonlySet<string>;
}) {
  const [open, setOpen] = useState(false);

  if (step.dedup_hit) {
    return (
      <p className="text-sm text-ink-muted">
        <span className="font-mono text-ink">{step.tool_name}</span> — same call as an earlier step
        — cached.
      </p>
    );
  }

  const docIdArg =
    step.tool_name === "read_document" && step.tool_args && typeof step.tool_args.doc_id === "string"
      ? (step.tool_args.doc_id as string)
      : null;

  return (
    <div>
      <p className="text-sm">
        <span className="font-mono font-medium text-ink">{step.tool_name}</span>{" "}
        <ToolArgs args={step.tool_args} />
      </p>
      {step.result_summary ? <p className="mt-1 text-sm text-ink-muted">{step.result_summary}</p> : null}
      {docIdArg ? (
        <p className="mt-1 text-xs">
          <EvidenceList evidenceIds={[docIdArg]} knownDocIds={knownDocIds} />
          <span className="ml-1 text-ink-muted">opened</span>
        </p>
      ) : null}
      {step.result !== null && step.result !== undefined ? (
        <>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="relative mt-1 text-xs font-medium text-ink-muted underline decoration-dotted after:absolute after:-inset-1.5 after:content-[''] hover:text-ink"
          >
            {open ? "Hide full result" : "Show full result"}
          </button>
          {open ? (
            <pre className="mt-1 max-h-72 overflow-y-auto rounded bg-ink p-3 text-xs text-primary-foreground">
              {typeof step.result === "string" ? step.result : JSON.stringify(step.result, null, 2)}
            </pre>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
