// Developer review note, 2026-10-10: rebuilt from a collapsible Accordion
// into individually-centered cards, matching the rest of the Method
// page's cards (an Accordion.Trigger is a `flex` row, which ignores an
// ancestor's `text-center`). No longer needs "use client" — a plain list
// doesn't build a React-elements array to pass across the Server/Client
// boundary the way Accordion's `items` prop did.
//
// T16c follow-up: the card grid became a definition list, the same
// treatment Guardrails and "Verifiable tonnes and risk band" now get on
// this page — these entries are label+definition pairs, not prose, and
// three cards abreast forced the body text into narrow ragged columns.
// The check notation (C1, C2a, ...) is set in Inter, larger and bold, at
// the developer's request: it is the one place on the page where an
// identifier is the thing being looked up, so it leads its own row.
// `font-ui` is the existing Inter token (app/globals.css, lib/fonts.ts);
// every other face on the page stays Google Sans.

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
      "FY-to-date certified tonnes must not exceed weighbridge-verified inbound tonnage by more than a 2% tolerance (ASSUMPTION, C2A_SHORTFALL_TOL). That tolerance absorbs ordinary per-shipment weighbridge measurement noise, not a real shortfall.",
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
      "Implied average transit speed (distance ÷ time between dispatch and weighbridge arrival) must not exceed 55 km/h (ASSUMPTION, MAX_AVG_SPEED_KMPH). If an e-way bill doesn't print a distance, we fall back to the straight-line distance with a 1.3× road-detour factor (ASSUMPTION, ROAD_FACTOR). The e-way bill's own validity window is also checked against the GST rule: one day of validity for every 200 km or part thereof (Rule-derived, EWB_KM_PER_DAY).",
  },
  {
    id: "C4",
    name: "Cross-document consistency",
    severity: "Hard",
    body:
      "Invoice quantity must match the e-way bill quantity within 1% (ASSUMPTION, QTY_TOL_DOC), and weighbridge net must match invoice quantity within 2% (ASSUMPTION, QTY_TOL_WEIGHBRIDGE). GSTIN and vehicle number must also agree across a shipment's documents.",
  },
  {
    id: "C5",
    name: "Duplicate document use",
    severity: "Hard",
    body:
      "An e-way bill, weighbridge ticket or invoice number can't be reused, not within one processor's dossier and not across processors. This comes straight from document uniqueness, so there's no tolerance.",
  },
  {
    id: "C6",
    name: "Consent validity and permitted category",
    severity: "Hard",
    body:
      "Activity must fall within the Consent to Operate's validity dates and permitted waste categories. This comes straight from the consent document itself, so there's no tolerance. Certified tonnes in a category the consent doesn't permit are excluded from the verifiable basis entirely, not just flagged.",
  },
  {
    id: "C7",
    name: "Electricity plausibility",
    severity: "Soft, recyclers only",
    body:
      "Electricity consumption per tonne processed must fall between 150 and 1,200 kWh/t (ASSUMPTION, KWH_PER_T_MIN/MAX). Falling outside that band in either direction isn't plausible for a recycling process.",
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
    <dl className="mx-auto mt-4 max-w-4xl divide-y divide-border text-left">
      {CHECKS.map((c) => (
        <div
          key={c.id}
          className="grid gap-x-10 gap-y-1 py-4 first:pt-0 last:pb-0 sm:grid-cols-[minmax(0,15rem)_minmax(0,1fr)]"
        >
          <dt>
            <span className="font-ui text-2xl font-bold text-ink">{c.id}</span>
            <span className="mt-0.5 block text-balance font-semibold text-method-body text-ink">{c.name}</span>
            <span className="mt-0.5 block text-xs uppercase tracking-wide text-ink-muted">{c.severity}</span>
          </dt>
          <dd className="text-pretty text-method-body text-ink-muted">{c.body}</dd>
        </div>
      ))}
    </dl>
  );
}
