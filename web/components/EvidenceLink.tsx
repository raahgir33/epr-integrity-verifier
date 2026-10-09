"use client";

import Link from "next/link";
import { resolveEvidence } from "@/lib/evidence";
import { useDocumentPanel } from "@/lib/document-panel-context";

/** T13.5c plan, Audit Batch 6: the two clickable chip variants below get
 * a small invisible hit-area extension (`after:-inset-0.5`, 2px each
 * side) rather than the usual 40px floor — chips wrap at only a 6px gap
 * (`gap-1.5` on the parent), so a larger extension would overlap the
 * next chip's own hit area (surfaces.md's collision rule: shrink rather
 * than let two hit areas overlap). The plain (non-clickable) variant is
 * untouched. */
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
              className="relative rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-xs text-ink underline decoration-dotted after:absolute after:-inset-0.5 after:content-[''] hover:bg-surface-sunk"
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
            className="relative rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-xs text-ink underline decoration-dotted after:absolute after:-inset-0.5 after:content-[''] hover:bg-surface-sunk"
          >
            {resolved.label}
          </Link>
        );
      })}
    </span>
  );
}
