// Committed e2e fixture API server (web/e2e). Plain Node http, no GCP/Gemini,
// no dependency on the real api/ service — started by playwright.config.ts's
// webServer entry only for the e2e suite. Serves just the endpoints the
// processor detail page needs for processor "PWP-05", with a deliberately
// long reasoning-steps list (14 steps, several with long unbroken tool-arg
// values and multi-sentence explanations) so expanding every step at once
// is a genuine stress case for the docked reasoning panel's layout, not a
// token one that happens to fit.
import http from "node:http";

const PORT = Number(process.env.FIXTURE_PORT ?? 4100);
const META = { seed: 42, facts_source: "truth" };

const PROFILE = {
  processor_id: "PWP-05",
  name: "Vindhya Waste Processors Pvt Ltd",
  type: "recycler",
  capacity_t_per_year: 4800,
  permitted_categories: ["post_consumer_pet", "post_consumer_hdpe"],
  consent_no: "CTO-MH-2022-00417",
  consent_valid_from: "01/04/2022",
  consent_valid_to: "31/03/2028",
  registration_no: "REG-MH-00417",
  gstin: "27AASYN1234A1Z5",
  address: "Survey No. 22, Industrial Estate, Indore, Madhya Pradesh",
  lat: 19.07,
  lon: 72.87,
};

function stage(certified, verifiable, risk) {
  return {
    certified_t: certified,
    verified_inbound_t: certified,
    capacity_limit_t: certified * 1.2,
    verifiable_t: verifiable,
    unverifiable_t: certified - verifiable,
    risk_band: risk,
  };
}

const CHECKS_ONLY = stage(6240.0, 3567.8, "High");

function checkResult(id, status, severity, source, explanation, extra) {
  return {
    check_id: id,
    status,
    severity,
    measured: extra?.measured ?? null,
    threshold: extra?.threshold ?? null,
    affected_tonnes: extra?.affected_tonnes ?? null,
    evidence_ids: extra?.evidence_ids ?? [],
    explanation,
    source,
  };
}

const CHECK_RESULTS = [
  checkResult("C1", "pass", "Hard", "Consent to Operate", "Certified tonnes stay within consented capacity."),
  checkResult(
    "C2a",
    "fail",
    "Hard",
    "ASSUMPTION",
    "Certified tonnes exceed weighbridge-verified inbound waste by more than the 2% tolerance.",
    { measured: 6240.0, threshold: 3673.4, affected_tonnes: 2672.2, evidence_ids: ["PWP-05-EXT-SHP-015"] },
  ),
];

const FINDINGS = [
  {
    finding_type: "unverified_weighbridge_gap",
    classification: "deductible",
    effect: "raises_concern",
    affected_tonnes: 2672.2,
    cited_shipment_ids: ["PWP-05-EXT-SHP-015"],
    evidence_ids: ["PWP-05-EXT-SHP-015"],
    explanation: "Certified tonnes exceed verified inbound waste for this batch.",
    disputed_by: null,
    agreement: "confirmed",
  },
];

// A long, space-free token in a tool arg — the kind of value (a composite
// evidence key, a long file path) that cannot wrap at a space and is the
// most likely thing to force horizontal growth of an ancestor flex/grid
// track if any of them is missing a min-width: 0 escape hatch.
const LONG_TOKEN =
  "PWP-05-EXT-SHP-015-weighbridge-slip-image-full-resolution-export-batch-2023-06-reconciliation-reference";

function longExplanation(i) {
  return (
    `Certificate batch 2023-0${(i % 9) + 1} reports a certified tonnage that the ` +
    `weighbridge-verified inbound waste for the same window does not support, once the ` +
    `${(i % 9) + 1}% measurement tolerance from C2A_SHORTFALL_TOL is applied. The gap persists ` +
    `after re-checking the e-way bill, the invoice line items, and the consent permit's ` +
    `category list, so it is treated as a genuine shortfall rather than ordinary per-shipment noise.`
  );
}

function reasoningSteps() {
  const steps = [];
  let idx = 0;

  steps.push({
    step_index: idx++,
    step_type: "hypothesis",
    tool_name: null,
    tool_args: null,
    output: {
      conclusions: Array.from({ length: 6 }, (_, i) => ({
        certificate_batch: `2023-0${(i % 9) + 1}`,
        status: i % 2 === 0 ? "unsupported" : "supported",
        evidence_ids: ["PWP-05-EXT-SHP-015"],
        explanation: longExplanation(i),
      })),
      findings: [
        {
          finding_type: "unverified_weighbridge_gap",
          effect: "raises_concern",
          cited_shipment_ids: ["PWP-05-EXT-SHP-015"],
          evidence_ids: ["PWP-05-EXT-SHP-015"],
          explanation: longExplanation(0),
        },
      ],
    },
    result: null,
    result_summary: null,
    latency_ms: 1840,
    tokens: { input: 3421, output: 512 },
    dedup_hit: false,
  });

  for (let i = 0; i < 5; i++) {
    steps.push({
      step_index: idx++,
      step_type: "critic_tool",
      tool_name: "read_document",
      tool_args: { doc_id: "PWP-05-EXT-SHP-015", reference: LONG_TOKEN, page: i + 1 },
      output: null,
      result: {
        doc_id: "PWP-05-EXT-SHP-015",
        doc_type: "weighbridge_slip",
        note: longExplanation(i),
        raw_line: LONG_TOKEN,
      },
      result_summary: `Read the weighbridge slip image for shipment PWP-05-EXT-SHP-015, page ${i + 1} of 5.`,
      latency_ms: 920 + i * 40,
      tokens: { input: 1203, output: 88 },
      dedup_hit: false,
    });
  }

  steps.push({
    step_index: idx++,
    step_type: "critic_final",
    tool_name: null,
    tool_args: null,
    output: {
      verdicts: Array.from({ length: 4 }, (_, i) => ({
        hypothesis_finding_index: 0,
        verdict: i % 2 === 0 ? "upheld" : "rejected",
        reason: longExplanation(i),
      })),
      objections: [
        {
          finding_type: "unverified_weighbridge_gap",
          explanation: longExplanation(6),
          evidence_ids: ["PWP-05-EXT-SHP-015"],
        },
      ],
    },
    result: null,
    result_summary: null,
    latency_ms: 1510,
    tokens: { input: 2884, output: 301 },
    dedup_hit: false,
  });

  steps.push({
    step_index: idx++,
    step_type: "revision",
    tool_name: null,
    tool_args: null,
    output: {
      revisions: Array.from({ length: 4 }, (_, i) => ({
        objection_index: 0,
        accepted: i % 2 === 0,
        explanation: longExplanation(i + 1),
      })),
      hypothesis_finding_responses: [{ hypothesis_finding_index: 0, decision: "accepted", explanation: longExplanation(2) }],
    },
    result: null,
    result_summary: null,
    latency_ms: 1200,
    tokens: { input: 2100, output: 240 },
    dedup_hit: false,
  });

  steps.push({
    step_index: idx++,
    step_type: "score",
    tool_name: null,
    tool_args: null,
    output: {
      checks_only_verifiable_t: 3567.8,
      full_verifiable_t: 3567.8,
      deducted_shipments: [{ shipment_id: "PWP-05-EXT-SHP-015", weighbridge_net_t: 2672.2 }],
      risk_band_before: "Medium",
      risk_band_after: "High",
    },
    result: null,
    result_summary: null,
    latency_ms: 40,
    tokens: null,
    dedup_hit: false,
  });

  return steps;
}

function documents() {
  return [
    { doc_id: "PWP-05-INV-0001", doc_type: "invoice", lang: "en", extraction_status: "ok" },
    { doc_id: "PWP-05-EWB-0001", doc_type: "eway_bill", lang: "en", extraction_status: "ok" },
    { doc_id: "PWP-05-WB-0001", doc_type: "weighbridge_slip", lang: "en", extraction_status: "ok" },
    { doc_id: "PWP-05-CTO-0001", doc_type: "consent_to_operate", lang: "en", extraction_status: "ok" },
  ];
}

function monthlyFlow() {
  const months = ["2023-04", "2023-05", "2023-06", "2023-07", "2023-08", "2023-09"];
  return months.map((m, i) => ({
    month: m,
    certified_t: 980 + i * 20,
    verified_inbound_t: 930 + i * 15,
  }));
}

const ROUTES = {
  "/processors/PWP-05": () => ({
    meta: META,
    profile: PROFILE,
    checks_only: CHECKS_ONLY,
    full: CHECKS_ONLY,
    agent_status: "ok",
    monthly_flow: monthlyFlow(),
    findings: FINDINGS,
    check_results: CHECK_RESULTS,
  }),
  "/processors/PWP-05/documents": () => ({ meta: META, processor_id: "PWP-05", documents: documents() }),
  "/processors/PWP-05/reasoning": () => ({
    meta: META,
    processor_id: "PWP-05",
    agent_status: "ok",
    tool_cap_reached: false,
    steps: reasoningSteps(),
    findings: FINDINGS,
  }),
  "/processors/PWP-05/site": () => ({
    processor_id: "PWP-05",
    building_count: 4,
    total_footprint_m2: 720,
    measured: 4800 / 720,
    status: "pass",
    severity: "Soft",
    threshold: 10,
    explanation: "Open Buildings footprint within 150m of the registered site supports the claimed capacity.",
    disclaimer: "Locations are illustrative and rounded; this is synthetic demo data.",
    sentinel_attribution: "Contains modified Copernicus Sentinel data",
    open_buildings_attribution: "Google Research Open Buildings (CC-BY-4.0)",
    thumb_bbox: [72.86, 19.06, 72.88, 19.08],
    meta: META,
  }),
  "/demo-batches": () => ({ meta: META, batches: [] }),
  "/alerts": () => ({ meta: META, alerts: [] }),
};

function notFound(res) {
  res.writeHead(404, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ detail: "not found" }));
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);

  if (url.pathname.startsWith("/documents/") && url.pathname.endsWith("/facts")) {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ doc_id: url.pathname.split("/")[2], fields: [] }));
    return;
  }

  if (url.pathname.startsWith("/processors/") && url.pathname.endsWith("/memo")) {
    notFound(res);
    return;
  }

  const handler = ROUTES[url.pathname];
  if (!handler) {
    notFound(res);
    return;
  }
  res.writeHead(200, { "Content-Type": "application/json" });
  res.end(JSON.stringify(handler()));
});

server.listen(PORT, () => {
  console.log(`e2e fixture API listening on ${PORT}`);
});
