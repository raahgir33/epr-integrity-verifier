import Link from "next/link";
import { resolveEvidence } from "@/lib/evidence";

export function EvidenceList({
  evidenceIds,
  knownDocIds,
}: {
  evidenceIds: string[];
  knownDocIds: ReadonlySet<string>;
}) {
  if (evidenceIds.length === 0) return null;

  return (
    <span className="inline-flex flex-wrap gap-1.5">
      {evidenceIds.map((id) => {
        const resolved = resolveEvidence(id, knownDocIds);
        if (resolved.kind === "plain") {
          return (
            <span
              key={id}
              className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-xs text-slate-600"
            >
              {resolved.label}
            </span>
          );
        }
        return (
          <Link
            key={id}
            href={resolved.href}
            target={resolved.kind === "document" ? "_blank" : undefined}
            rel={resolved.kind === "document" ? "noopener noreferrer" : undefined}
            className="rounded border border-slate-300 bg-white px-1.5 py-0.5 font-mono text-xs text-slate-700 underline decoration-dotted hover:bg-slate-50"
          >
            {resolved.label}
          </Link>
        );
      })}
    </span>
  );
}
