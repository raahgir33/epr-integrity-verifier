"use client";

import Link from "next/link";
import { resolveEvidence } from "@/lib/evidence";
import { useDocumentPanel } from "@/lib/document-panel-context";

export function EvidenceList({
  evidenceIds,
  knownDocIds,
}: {
  evidenceIds: string[];
  knownDocIds: ReadonlySet<string>;
}) {
  const openDocument = useDocumentPanel();
  if (evidenceIds.length === 0) return null;

  return (
    <span className="inline-flex flex-wrap gap-1.5">
      {evidenceIds.map((id) => {
        const resolved = resolveEvidence(id, knownDocIds);
        if (resolved.kind === "plain") {
          return (
            <span
              key={id}
              className="rounded border border-border bg-surface-sunk px-1.5 py-0.5 font-mono text-xs text-ink-muted"
            >
              {resolved.label}
            </span>
          );
        }
        if (resolved.kind === "document" && openDocument) {
          return (
            <button
              key={id}
              type="button"
              onClick={() => openDocument(id)}
              className="rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-xs text-ink underline decoration-dotted hover:bg-surface-sunk"
            >
              {resolved.label}
            </button>
          );
        }
        return (
          <Link
            key={id}
            href={resolved.href}
            target={resolved.kind === "document" ? "_blank" : undefined}
            rel={resolved.kind === "document" ? "noopener noreferrer" : undefined}
            className="rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-xs text-ink underline decoration-dotted hover:bg-surface-sunk"
          >
            {resolved.label}
          </Link>
        );
      })}
    </span>
  );
}
