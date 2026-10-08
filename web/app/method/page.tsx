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

export default function MethodPage() {
  return (
    <div className="space-y-10">
      <div>
        <h1 className="font-display text-2xl font-semibold text-slate-900">Method</h1>
        <p className="mt-1 text-sm text-slate-600">
          How verifiable tonnes are computed, what each check does, how the agent loop reasons, and what
          this system does not (yet) prove.
        </p>
      </div>

      <section>
        <h2 className="font-display text-lg font-semibold text-slate-900">1. Deterministic checks</h2>
        <p className="mt-2 text-sm text-slate-600">
          Every threshold below lives in <code>app/checks/params.py</code>, each labelled as either
          rule-derived (cited to a regulation or document convention) or an explicit assumption. A
          failed <strong>hard</strong> check can never be overruled by an agent; a <strong>soft</strong>{" "}
          check can raise the risk band by at most one step.
        </p>
        <ul className="mt-4 space-y-4">
          {CHECKS.map((c) => (
            <li key={c.id}>
              <p className="text-sm">
                <span className="font-mono font-semibold text-slate-900">{c.id}</span>{" "}
                <span className="font-medium text-slate-900">{c.name}</span>{" "}
                <span className="text-xs uppercase tracking-wide text-slate-400">{c.severity}</span>
              </p>
              <p className="mt-0.5 text-sm text-slate-600">{c.body}</p>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="font-display text-lg font-semibold text-slate-900">2. Verifiable tonnes and risk band</h2>
        <div className="mt-2 space-y-2 text-sm text-slate-600">
          <p>
            <strong className="text-slate-900">Verified inbound tonnes</strong> — weighbridge-net tonnes
            of shipments that pass C3, C4 and C5, minus shipments an agreed agent finding deducts.
          </p>
          <p>
            <strong className="text-slate-900">Capacity limit</strong> — consented capacity × months
            elapsed ÷ 12, zero for any month outside the consent&apos;s validity window (C6).
          </p>
          <p>
            <strong className="text-slate-900">Verifiable tonnes</strong> — the minimum of eligible
            certified tonnes (certified tonnes excluding any out-of-consent category), verified inbound
            tonnes, and the capacity limit.
          </p>
          <p>
            <strong className="text-slate-900">Unverifiable tonnes</strong> — certified tonnes minus
            verifiable tonnes.
          </p>
          <p>
            <strong className="text-slate-900">Risk band</strong> — Low under 5% unverifiable, Medium
            5–25%, High over 25%. Each failed soft check (C2b, C7, C8), or any non-empty review-flag,
            systemic-finding or no-own-evidence finding list, raises the band by one step — never more
            than one step in total, however many of these signals fire together.
          </p>
        </div>
      </section>

      <section>
        <h2 className="font-display text-lg font-semibold text-slate-900">3. The agent loop</h2>
        <div className="mt-2 space-y-2 text-sm text-slate-600">
          <p>
            Deterministic checks catch what arithmetic and document fields can prove. The agent loop
            exists for what they can&apos;t: reading meaning in free text, connecting evidence across a
            whole dossier, and challenging a first conclusion before it&apos;s trusted.
          </p>
          <p>
            A <strong className="text-slate-900">Hypothesis</strong> agent reads a compact digest of the
            processor&apos;s dossier — profile, consent terms, monthly material flow, every check result
            with its evidence, the site result, and every distinct inbound item description — and judges
            each certificate batch (calendar month) as supported, partly supported or unsupported, with
            its own proposed findings.
          </p>
          <p>
            A <strong className="text-slate-900">Critic</strong> agent then runs a tool-calling loop
            (inspecting check results, shipments, document facts, the site assessment, and reading a
            document&apos;s own bytes directly) to challenge or confirm the Hypothesis, then issues a
            verdict on every one of the Hypothesis&apos;s own findings and raises any new objections of
            its own.
          </p>
          <p>
            The Hypothesis gets one revision round — accept or reject each Critic objection, maintain or
            withdraw each of its own disputed findings.
          </p>
          <p>
            <strong className="text-slate-900">Two agents must agree before a finding is deducted.</strong>{" "}
            A finding neither agent disputes becomes a deduction; one they disagree on, or that the other
            agent never addressed, becomes a visible review flag instead — never a silent deduction, and
            never silently dropped.
          </p>
          <p className="font-medium text-slate-900">Guards enforced in code, not left to the prompt:</p>
          <ul className="list-disc space-y-1 pl-5">
            <li>
              <strong>Own-evidence rule</strong> — every shipment a finding cites must have at least one
              of its own documents (invoice, e-way bill or weighbridge slip) among that finding&apos;s
              evidence, or the finding is kept but not deducted.
            </li>
            <li>
              <strong>Systemic-finding guard</strong> — a finding citing more than half the processor&apos;s
              verified shipments is too broad to deduct automatically; it&apos;s kept and flagged for
              review instead.
            </li>
            <li>
              <strong>Concurs-with-check rule</strong> — a finding that only restates what a deterministic
              check already caught adds no second deduction and no second risk-band bump.
            </li>
            <li>
              <strong>Hard checks are final</strong> — no agent finding can overrule a failed hard check.
            </li>
            <li>
              <strong>The language model never does arithmetic that matters</strong> — every tonnage
              figure and the risk band are computed deterministically from the agents&apos; structured
              findings; the model only writes the plain-language narrative from numbers already computed.
            </li>
          </ul>
        </div>
      </section>

      <section>
        <h2 className="font-display text-lg font-semibold text-slate-900">4. Evaluation protocol</h2>
        <div className="mt-2 space-y-2 text-sm text-slate-600">
          <p>
            A held-out test set, generated the same way as the development set but with a different seed,
            is never used while building or tuning the system. Before it is generated, every check
            threshold and every agent prompt is frozen (tagged <code>eval-freeze</code>) so nothing is
            tuned against it afterwards.
          </p>
          <p>
            The full pipeline — extraction, normalisation, checks, agents — runs once on the held-out set.
            Reported metrics: extraction field accuracy against the seeded ground truth, detection
            precision and recall against the seeded issue types, and the measured gain of the full system
            (checks plus agents) over deterministic checks alone. The <a href="/evaluation" className="underline decoration-dotted">Evaluation</a>{" "}
            page reports these once the held-out run has completed; development-set numbers, where shown
            anywhere, are always labelled as such.
          </p>
        </div>
      </section>

      <section>
        <h2 className="font-display text-lg font-semibold text-slate-900">5. Limitations</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">
          <li>
            Every processor, document, brand and certificate shown here is synthetic and fictional — no
            real company, recycler or brand is represented or implicated.
          </li>
          <li>
            C3 (transport plausibility) is exercised only by hand-built test fixtures; no scenario in the
            seeded demonstration dataset trips it, so its behaviour on real documents is unproven here.
          </li>
          <li>
            Site coordinates are illustrative, rounded to two decimal places, with no street address shown
            — they should not be read as real locations.
          </li>
          <li>
            Open Buildings is a single snapshot from imagery processed in 2023; it does not reflect any
            construction or demolition since.
          </li>
        </ul>
      </section>

      <section>
        <h2 className="font-display text-lg font-semibold text-slate-900">6. Data sources and attribution</h2>
        <p className="mt-2 text-sm text-slate-600">Contains modified Copernicus Sentinel data (2023).</p>
        <p className="text-sm text-slate-600">Open Buildings v3, Google Research — CC BY 4.0.</p>
      </section>
    </div>
  );
}
