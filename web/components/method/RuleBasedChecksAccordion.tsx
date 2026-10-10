// Developer review note, 2026-10-10: rebuilt from a collapsible Accordion
// into a grid of individually-centered cards, matching the rest of the
// Method page's cards (an Accordion.Trigger is a `flex` row, which
// ignores an ancestor's `text-center` — ours was the one section on the
// page that didn't visually center). No longer needs "use client" — a
// plain centered-card grid doesn't build a React-elements array to pass
// across the Server/Client boundary the way Accordion's `items` prop did.
//
// Round 4: 10% more corner rounding (Tailwind v4's default --radius-md
// is 6px, so 6px * 1.1 = 6.6px, expressed as an arbitrary value since
// 6.6px isn't one of Tailwind's own radius steps).
//
// Round 5: a hover scale was tried (first height-only, then uniform) and
// the developer didn't like either, so there's no transform on hover at
// all now, only a resting -> raised shadow bump for a little depth. The
// border went back to a plain hairline (border, not border-2) per the
// same note. auto-rows-fr on the grid still keeps every card in a row
// equal height regardless of body-text length.

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
    <div className="grid auto-rows-fr grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {CHECKS.map((c) => (
        <div
          key={c.id}
          className="flex flex-col justify-center rounded-[6.6px] border border-border p-4 text-center shadow-resting transition-shadow duration-200 ease-out hover:shadow-raised"
        >
          <p>
            <span className="font-mono font-semibold text-method-body text-ink">{c.id}</span>{" "}
            <span className="font-medium text-method-body text-ink">{c.name}</span>
          </p>
          <p className="mt-1 text-xs uppercase tracking-wide text-ink-muted">{c.severity}</p>
          <p className="mt-2 text-pretty text-method-body text-ink-muted">{c.body}</p>
        </div>
      ))}
    </div>
  );
}
