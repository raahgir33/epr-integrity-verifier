"use client";

import { useState } from "react";
import { EvidenceList } from "@/components/EvidenceLink";
import type { HypothesisOutput } from "@/lib/reasoning";
import { formatMonth } from "@/lib/format";

const STATUS_LABEL: Record<string, string> = {
  supported: "Supported",
  partly_supported: "Partly supported",
  unsupported: "Unsupported",
};

export function HypothesisStep({
  output,
  knownDocIds,
}: {
  output: HypothesisOutput;
  knownDocIds: ReadonlySet<string>;
}) {
  const [showAll, setShowAll] = useState(false);
  const flagged = output.conclusions.filter((c) => c.status !== "supported");
  const supported = output.conclusions.filter((c) => c.status === "supported");
  const visible = showAll ? output.conclusions : flagged;

  return (
    <div>
      <ul className="space-y-2">
        {visible.map((c) => (
          <li key={c.certificate_batch} className="text-sm">
            <span className="font-medium text-ink">{formatMonth(c.certificate_batch)}</span>{" "}
            <span className="text-ink-muted">— {STATUS_LABEL[c.status] ?? c.status}</span>
            <p className="text-ink-muted">{c.explanation}</p>
            {c.evidence_ids.length > 0 ? (
              <div className="mt-0.5">
                <EvidenceList evidenceIds={c.evidence_ids} knownDocIds={knownDocIds} />
              </div>
            ) : null}
          </li>
        ))}
      </ul>
      {supported.length > 0 ? (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="mt-2 text-xs font-medium text-ink-muted underline decoration-dotted hover:text-ink"
        >
          {showAll ? "Hide supported months" : `Show all ${output.conclusions.length} months`}
        </button>
      ) : null}

      {output.findings.length > 0 ? (
        <div className="mt-3 border-t border-border pt-3">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">Proposed findings</p>
          <ul className="mt-1 space-y-2">
            {output.findings.map((f, i) => (
              <li key={i} className="text-sm">
                <span className="font-medium text-ink">{f.finding_type}</span>
                <p className="text-ink-muted">{f.explanation}</p>
                {f.evidence_ids.length > 0 ? (
                  <div className="mt-0.5">
                    <EvidenceList evidenceIds={f.evidence_ids} knownDocIds={knownDocIds} />
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
