"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { EvidenceList } from "@/components/EvidenceLink";
import type { CheckResultOut } from "@/lib/api";
import { formatCheckValue, STATUS_LABEL, STATUS_TONE } from "@/lib/checks";
import { checkName } from "@/lib/labels";

/** One card in the Checks tab's compact grid (T13.5 plan, Part 4) —
 * status/severity/one-line result always visible; measured/threshold/
 * evidence only once expanded.
 *
 * T16c F12: the check's plain name sits beside its code, so a check reads
 * the same here as it does on the Method page. T16c F27: the card is a
 * disclosure, so it carries the same ChevronDown the Accordion and the
 * reasoning log rows use — previously nothing indicated it opened. */
export function CheckCard({ check, knownDocIds }: { check: CheckResultOut; knownDocIds: ReadonlySet<string> }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="card p-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full flex-col items-start gap-1 text-left"
      >
        <div className="flex w-full items-start justify-between gap-2">
          <span className="min-w-0">
            <span className="font-mono text-sm font-semibold text-ink">{check.check_id}</span>
            <span className="ml-2 text-sm font-medium text-ink">{checkName(check.check_id)}</span>
          </span>
          <span className="flex shrink-0 items-center gap-1.5">
            <span className={`text-sm font-medium ${STATUS_TONE[check.status] ?? "text-ink-muted"}`}>
              {STATUS_LABEL[check.status] ?? check.status}
            </span>
            <ChevronDown
              aria-hidden
              size={16}
              className={`text-ink-muted transition-transform duration-200 ${open ? "rotate-180" : ""}`}
            />
          </span>
        </div>
        <span className="text-xs uppercase tracking-wide text-ink-muted">{check.severity}</span>
        <p className="mt-1 line-clamp-2 text-sm text-ink">{check.explanation}</p>
      </button>

      {open ? (
        <div className="mt-3 border-t border-border pt-3 text-sm">
          <p className="text-ink-muted">
            Measured {formatCheckValue(check.check_id, check.measured)} · Threshold{" "}
            {formatCheckValue(check.check_id, check.threshold)}{" "}
            <span className="text-ink-muted/80">({check.source})</span>
          </p>
          {check.evidence_ids.length > 0 ? (
            <div className="mt-2 text-xs">
              <span className="mr-1.5 font-medium text-ink-muted">Evidence:</span>
              <EvidenceList evidenceIds={check.evidence_ids} knownDocIds={knownDocIds} />
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
