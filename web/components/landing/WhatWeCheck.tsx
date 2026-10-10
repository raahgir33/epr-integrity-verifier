import type { CheckCatalogEntry } from "@/lib/landing";

/** Plain-English description of what each check tests — deliberately no
 * numbers or thresholds (those live only in app/checks/params.py and
 * the per-processor check result itself, never duplicated here). Keyed
 * by check_id; an id with no entry still renders via the fallback, so a
 * check added to the pipeline later appears automatically even before
 * this map is updated for it. */
const DESCRIPTIONS: Record<string, string> = {
  C1: "Tests whether a processor's certified tonnes stay within its own consented capacity for the year.",
  C2a: "Tests whether certified tonnes are backed by material actually received, confirmed by weighbridge records.",
  C2b: "Tests whether a recycler's sold output is plausible given how much material it processed.",
  C3a: "Tests whether a shipment's recorded transit time between dispatch and weighbridge arrival is physically plausible.",
  C3b: "Tests an e-way bill's own validity window against its weighbridge arrival time.",
  C4: "Tests whether quantities, GSTIN and vehicle details agree across a shipment's own documents.",
  C5: "Tests whether an e-way bill, weighbridge ticket or invoice number has been reused.",
  C6: "Tests whether activity falls within the consent's validity window and permitted waste categories.",
  C7: "Tests whether a recycler's electricity use is plausible for the tonnage it processed.",
  C8: "Tests whether satellite-derived building footprint at the registered site can plausibly support the claimed capacity.",
  AGENT_SYSTEMIC_FINDING: "Flags an agent finding too broad to deduct automatically because it touches most of a processor's verified shipments.",
  AGENT_NO_OWN_EVIDENCE_FINDING: "Flags an agent finding that lacks its own shipment-level documentary evidence.",
  AGENT_DISPUTED_FINDING: "Flags a finding the Hypothesis and Critic agents disagreed on.",
};

const FALLBACK_DESCRIPTION = "A deterministic check in the pipeline. See /method for the full description.";

/** T13.5c plan, Batch 0.12/13: explicit check order (C1 first), since
 * buildCheckCatalog's own localeCompare sort would put the "AGENT_*"
 * entries before "C1" alphabetically. Anything not in this list falls
 * back to the existing locale sort, preserving buildCheckCatalog's own
 * "a check added to the pipeline later appears automatically" design. */
const CHECK_ORDER = ["C1", "C2a", "C2b", "C3a", "C3b", "C4", "C5", "C6", "C7", "C8"];

function orderedCatalog(catalog: CheckCatalogEntry[]): CheckCatalogEntry[] {
  return [...catalog].sort((a, b) => {
    const ia = CHECK_ORDER.indexOf(a.checkId);
    const ib = CHECK_ORDER.indexOf(b.checkId);
    if (ia !== -1 && ib !== -1) return ia - ib;
    if (ia !== -1) return -1;
    if (ib !== -1) return 1;
    return a.checkId.localeCompare(b.checkId);
  });
}

/** Rebuilt as a card grid (T13.5c plan, Batch 0.12/13), same visual
 * treatment as the Method page's Rule-Based Checks accordion rows
 * (`components/method/RuleBasedChecksAccordion.tsx`, left unchanged,
 * approved as is) — font-mono id, uppercase severity label — but as a
 * static, always-expanded 3/2/1-column grid of cards rather than a
 * collapsible accordion. */
export function WhatWeCheck({ catalog }: { catalog: CheckCatalogEntry[] }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {orderedCatalog(catalog).map((entry) => (
        <div key={entry.checkId} className="card p-4">
          <p>
            <span className="font-mono font-semibold text-ink">{entry.checkId}</span>{" "}
            <span className="text-xs uppercase tracking-wide text-ink-muted">{entry.severity}</span>
          </p>
          <p className="mt-2 text-sm text-ink-muted">{DESCRIPTIONS[entry.checkId] ?? FALLBACK_DESCRIPTION}</p>
        </div>
      ))}
    </div>
  );
}
