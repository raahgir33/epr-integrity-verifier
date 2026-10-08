"use client";

import { useState } from "react";
import { EvidenceList } from "@/components/EvidenceLink";
import type { ReasoningStepOut } from "@/lib/api";

function ToolArgs({ args }: { args: Record<string, unknown> | null }) {
  if (!args || Object.keys(args).length === 0) return null;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {Object.entries(args).map(([key, value]) => (
        <span key={key} className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-600">
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
      <p className="text-sm text-slate-500">
        <span className="font-mono text-slate-700">{step.tool_name}</span> — same call as an earlier step
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
        <span className="font-mono font-medium text-slate-900">{step.tool_name}</span>{" "}
        <ToolArgs args={step.tool_args} />
      </p>
      {step.result_summary ? <p className="mt-1 text-sm text-slate-600">{step.result_summary}</p> : null}
      {docIdArg ? (
        <p className="mt-1 text-xs">
          <EvidenceList evidenceIds={[docIdArg]} knownDocIds={knownDocIds} />
          <span className="ml-1 text-slate-500">opened</span>
        </p>
      ) : null}
      {step.result !== null && step.result !== undefined ? (
        <>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="mt-1 text-xs font-medium text-slate-500 underline decoration-dotted hover:text-slate-900"
          >
            {open ? "Hide full result" : "Show full result"}
          </button>
          {open ? (
            <pre className="mt-1 max-h-72 overflow-y-auto rounded bg-slate-900 p-3 text-xs text-slate-100">
              {typeof step.result === "string" ? step.result : JSON.stringify(step.result, null, 2)}
            </pre>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
