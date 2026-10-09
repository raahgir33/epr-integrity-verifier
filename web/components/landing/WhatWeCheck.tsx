"use client";
// "use client" is required here, not optional: Accordion's `items` prop
// carries React elements (trigger/content). Building that array in a
// Server Component and passing it across the RSC boundary into a Client
// Component reliably produced a spurious "missing key" warning on every
// render in dev (confirmed by bisection — the array itself always had
// correct, unique keys; moving the array's construction client-side,
// so no element instances cross the boundary as props, is what fixed
// it). Faq/AudienceTabs/ProcessorTabs hit the same pattern and get the
// same fix.

import { Accordion } from "@/components/ui/Accordion";
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

const FALLBACK_DESCRIPTION = "A deterministic check in the pipeline — see /method for the full description.";

export function WhatWeCheck({ catalog }: { catalog: CheckCatalogEntry[] }) {
  return (
    <Accordion
      items={catalog.map((entry) => ({
        id: entry.checkId,
        trigger: (
          <span>
            <span className="font-mono font-semibold text-ink">{entry.checkId}</span>{" "}
            <span className="text-xs uppercase tracking-wide text-ink-muted">{entry.severity}</span>
          </span>
        ),
        content: <p>{DESCRIPTIONS[entry.checkId] ?? FALLBACK_DESCRIPTION}</p>,
      }))}
    />
  );
}
