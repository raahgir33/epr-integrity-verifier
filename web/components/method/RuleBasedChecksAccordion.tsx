"use client";
// Required — see WhatWeCheck.tsx's identical comment: Accordion's `items`
// prop carries React elements (trigger/content), and building that array
// in a Server Component passed across the RSC boundary into a Client
// Component reliably produces a spurious "missing key" dev warning.
// MethodPage is a Server Component, so this one small piece — the only
// part of that page needing an items array — is split out here instead.

import { Accordion } from "@/components/ui/Accordion";

const CHECKS = [
  {
    id: "C1",
    name: "Certified tonnes within consented capacity",
    severity: "Hard",
    body:
      "FY-to-date certified tonnes must not exceed the processor's own consented capacity, pro-rated by months elapsed. The limit is a processor-specific fact from its Consent to Operate, not a tunable threshold.",
  },
  {
    id: "C2a",
    name: "Certified tonnes within verified inbound waste",
    severity: "Hard",
    body:
      "FY-to-date certified tonnes must not exceed weighbridge-verified inbound tonnage by more than a 2% tolerance (ASSUMPTION, C2A_SHORTFALL_TOL) — set to absorb ordinary per-shipment weighbridge measurement noise, not to excuse a real shortfall.",
  },
  {
    id: "C2b",
    name: "Recycled output within processed tonnes × yield",
    severity: "Soft, recyclers only",
    body:
      "Recycled output sold must not exceed processed tonnes times a 95% maximum yield ceiling (ASSUMPTION, MAX_YIELD_RECYCLER).",
  },
  {
    id: "C3",
    name: "Transport plausibility",
    severity: "Hard",
    body:
      "Implied average transit speed (distance ÷ time between dispatch and weighbridge arrival) must not exceed 55 km/h (ASSUMPTION, MAX_AVG_SPEED_KMPH); a straight-line-distance fallback with a 1.3× road-detour factor (ASSUMPTION, ROAD_FACTOR) applies only when an e-way bill's printed distance is missing. The e-way bill's own validity window is checked against the GST e-way bill rule — one day of validity per 200 km or part thereof (Rule-derived, EWB_KM_PER_DAY).",
  },
  {
    id: "C4",
    name: "Cross-document consistency",
    severity: "Hard",
    body:
      "Invoice quantity vs e-way bill quantity within 1% (ASSUMPTION, QTY_TOL_DOC); weighbridge net vs invoice quantity within 2% (ASSUMPTION, QTY_TOL_WEIGHBRIDGE); GSTIN and vehicle number must agree across a shipment's documents.",
  },
  {
    id: "C5",
    name: "Duplicate document use",
    severity: "Hard",
    body:
      "An e-way bill, weighbridge ticket or invoice number must not be reused — within one processor's dossier or across processors. Rule-derived from document uniqueness; no tolerance.",
  },
  {
    id: "C6",
    name: "Consent validity and permitted category",
    severity: "Hard",
    body:
      "Activity must fall within the Consent to Operate's validity dates and permitted waste categories. Rule-derived from the consent document itself; no tolerance. Certified tonnes in a category the consent doesn't permit are excluded from the verifiable basis entirely, not only flagged.",
  },
  {
    id: "C7",
    name: "Electricity plausibility",
    severity: "Soft, recyclers only",
    body:
      "Electricity consumption per tonne processed must fall between 150 and 1,200 kWh/t (ASSUMPTION, KWH_PER_T_MIN/MAX) — outside this band in either direction is implausible for a recycling process.",
  },
  {
    id: "C8",
    name: "Site plausibility",
    severity: "Soft",
    body:
      "Open Buildings polygons within 150 m of the registered site (ASSUMPTION, SITE_RADIUS_M), at confidence ≥ 0.75 (ASSUMPTION, MIN_BUILDING_CONFIDENCE), are summed into a footprint. Claimed capacity must not exceed 10 tonnes per m² of that footprint (ASSUMPTION, MAX_TPA_PER_M2).",
  },
];

export function RuleBasedChecksAccordion() {
  return (
    <Accordion
      items={CHECKS.map((c) => ({
        id: c.id,
        trigger: (
          <span>
            <span className="font-mono font-semibold text-ink">{c.id}</span>{" "}
            <span className="font-medium text-ink">{c.name}</span>{" "}
            <span className="text-xs uppercase tracking-wide text-ink-muted">{c.severity}</span>
          </span>
        ),
        content: <p className="max-w-[70ch]">{c.body}</p>,
      }))}
    />
  );
}
