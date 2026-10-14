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

// T16b: two modes from one data set. "processor" (the default) is the
// original behaviour this file was written for and must not change --
// e2e/error-boundary.spec.ts depends on "/processors" (the list route)
// being absent so the home page's getProcessors() 404s and the error
// boundary renders. "landing" adds exactly the routes the landing page
// needs, plus the live-run simulation below, and is served on its own
// port to a second Next instance (see playwright.config.ts).
const MODE = process.env.FIXTURE_MODE ?? "processor";

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

// --- T16b live-run simulation (landing mode only) -------------------
//
// A stateful GET /runs/{run_id} so the task-row panel can be driven
// start -> done and start -> failed without ever touching the deployed
// API (a real run calls Gemini, counts against the daily cap of 10 and
// mutates seed-42 demo data). Stage order, the status enum and the
// stage_timestamps shape are copied from app/events/run_processor.py --
// nothing here invents a stage the backend doesn't report.
//
// Durations are compressed (~1.2s a stage, not ~74s) so the e2e suite
// stays fast; they are otherwise the real shape, including the two
// windows the derived rows read:
//   * the alert is attached when the reasoning stage finishes;
//   * stage_timestamps.drafting_memo exists while status is still
//     "drafting_memo" -- the cache invalidate + preload window.
// Each stage must outlast the web app's 2.5s poll interval
// (lib/useRunPolling.ts), otherwise several stages complete between two
// polls and the intermediate states are never rendered at all -- the run
// jumps from "reading" to "everything done". A real run's stages take
// tens of seconds, so polling resolves every transition there; these are
// compressed, but not past the point where the thing being tested stops
// being observable.
const STAGE_MS = {
  reading_documents: 3200,
  checking: 2800,
  reasoning: 6000,
  drafting_memo: 3000,
};
const REFRESH_MS = 2600;
const STAGE_SEQUENCE = ["reading_documents", "checking", "reasoning", "drafting_memo"];

// A batch with no extra documents: the backend still calls
// finish_stage("reading_documents") unconditionally (run_processor.py's
// `if extra_document_ids:` guards only the work, not the timing call),
// so the stage lands in stage_timestamps with a near-zero duration
// rather than being absent. Pinned here so buildRunRows is exercised
// against the real shape.
const SKIPPED_READ_MS = 120;

const DEMO_BATCHES = [
  { batch_id: "BATCH-PWP-05-001", period_month: "2026-03", processor_id: "PWP-05", pushes_over_verifiable: true, quantity_t: 8.45 },
  { batch_id: "BATCH-PWP-05-NODOCS", period_month: "2026-04", processor_id: "PWP-05", pushes_over_verifiable: false, quantity_t: 1.92 },
  { batch_id: "BATCH-PWP-05-FAIL", period_month: "2026-02", processor_id: "PWP-05", pushes_over_verifiable: false, quantity_t: 3.07 },
  // Always refused with 429, mirroring the real API's cooldown gate, so
  // the card's error path can be exercised without a cooldown clock.
  { batch_id: "BATCH-PWP-05-COOLDOWN", period_month: "2026-01", processor_id: "PWP-05", pushes_over_verifiable: false, quantity_t: 0.64 },
];

// batch_id -> scenario. "fail:<stage>" dies in that stage; "fail:refresh"
// dies after drafting_memo finished, in the cache re-warm.
const BATCH_SCENARIO = {
  "BATCH-PWP-05-001": "done",
  "BATCH-PWP-05-NODOCS": "nodocs",
  "BATCH-PWP-05-FAIL": "fail:reasoning",
};

const ALERT = {
  alert_id: "ALERT-DEMO-0001",
  created_at: "2026-03-31T10:04:00Z",
  message: "Risk band rose from Medium to High after the new certificate batch.",
  new_finding_summary: "Certified tonnes exceed verified inbound waste for this batch.",
  processor_id: "PWP-05",
  risk_band_after: "High",
  risk_band_before: "Medium",
  run_id: "run-1",
};

const runs = new Map();
let runSeq = 0;

function stageMsFor(runState, stage) {
  if (stage === "reading_documents" && runState.scenario === "nodocs") return SKIPPED_READ_MS;
  return STAGE_MS[stage];
}

/** Rebuilds the run row exactly as GET /runs/{run_id} would report it at
 * `elapsed` ms into the run. Pure given (runState, elapsed). */
function runSnapshot(runState) {
  const elapsed = Date.now() - runState.startedAt;
  const failStage = runState.scenario.startsWith("fail:") ? runState.scenario.slice(5) : null;
  const allSteps = reasoningSteps();

  const stage_timestamps = {};
  let cursor = 0;
  let status = "queued";
  let steps = [];
  let alert = null;

  for (const stage of STAGE_SEQUENCE) {
    const span = stageMsFor(runState, stage);
    const startedAtMs = cursor;
    const endsAtMs = cursor + span;

    if (elapsed < startedAtMs) break;

    status = stage;

    if (stage === "reasoning") {
      // Steps stream in one at a time across the stage, so the panel's
      // reasoning sub-lines grow the way they do on a real run.
      const progress = Math.min(1, Math.max(0, (elapsed - startedAtMs) / span));
      steps = allSteps.slice(0, Math.max(1, Math.round(progress * allSteps.length)));
    }

    if (failStage === stage && elapsed >= startedAtMs + span / 2) {
      return {
        status: "failed",
        stage_timestamps,
        steps,
        alert,
        error_message: `${stage} failed: synthetic fixture failure`,
      };
    }

    if (elapsed < endsAtMs) {
      // `alert` is carried, not nulled: it is attached the moment the
      // reasoning stage finishes, so it is already present while
      // drafting_memo is still in flight -- which is exactly what the
      // derived "Alert decision" row reads.
      return { status, stage_timestamps, steps, alert, error_message: null };
    }

    stage_timestamps[stage] = {
      at: new Date(runState.startedAt + endsAtMs).toISOString(),
      duration_s: Math.round((span / 1000) * 10) / 10,
    };
    if (stage === "reasoning") {
      steps = allSteps;
      if (runState.scenario !== "noalert") alert = ALERT;
    }
    cursor = endsAtMs;
  }

  // Every stage has finished. status stays "drafting_memo" while the
  // cache invalidate + preload runs -- the window the "Refreshing
  // results" row reads -- then flips to done/failed.
  if (elapsed < cursor + REFRESH_MS) {
    return { status: "drafting_memo", stage_timestamps, steps, alert, error_message: null };
  }
  if (failStage === "refresh") {
    return { status: "failed", stage_timestamps, steps, alert, error_message: "cache preload failed: synthetic fixture failure" };
  }
  return { status: "done", stage_timestamps, steps, alert, error_message: null };
}

function runResponse(runId) {
  const runState = runs.get(runId);
  if (!runState) return null;
  const snap = runSnapshot(runState);
  return {
    meta: META,
    run_id: runId,
    batch_id: runState.batchId,
    processor_id: runState.processorId,
    status: snap.status,
    created_at: new Date(runState.startedAt).toISOString(),
    updated_at: new Date().toISOString(),
    stage_timestamps: snap.stage_timestamps,
    steps: snap.steps,
    error_message: snap.error_message,
    alert: snap.alert,
  };
}

const LANDING_ROUTES = {
  "/processors": () => ({
    meta: META,
    processors: [
      {
        processor_id: "PWP-05",
        name: PROFILE.name,
        type: PROFILE.type,
        agent_status: "ok",
        checks_only: CHECKS_ONLY,
        full: CHECKS_ONLY,
      },
    ],
  }),
  "/stats": () => ({
    meta: META,
    as_of: "2026-03-31",
    certified_t_total: 6240.0,
    unverifiable_t_total: 2672.2,
    documents_read: 714,
    fields_read: 5523,
    processors_count: 1,
    fy_label: "FY 2025-26",
    field_read_accuracy_pct: "99.96%",
    field_read_accuracy_value: 99.96,
    field_read_correct: 5521,
    field_read_total: 5523,
    field_read_dataset_label: "seed 42",
  }),
  "/demo-batches": () => ({ meta: META, batches: DEMO_BATCHES }),
  // One historical alert, so the page-level AlertBanner (app/page.tsx)
  // renders and can be asserted untouched by the live-run panel.
  "/alerts": () => ({
    meta: META,
    alerts: [
      ALERT,
      { ...ALERT, alert_id: "ALERT-DEMO-0002", risk_band_before: "High", risk_band_after: "Medium",
        message: "Risk band eased from High to Medium after the new certificate batch." },
      { ...ALERT, alert_id: "ALERT-DEMO-0003", risk_band_before: "Medium", risk_band_after: "Low",
        message: "Risk band eased from Medium to Low after the new certificate batch." },
      { ...ALERT, alert_id: "ALERT-DEMO-0004", risk_band_before: null, risk_band_after: null,
        message: "A new finding surfaced; risk band unchanged." },
    ],
  }),
};

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
  res.end(JSON.stringify({ error: "not found", request_id: "fixture" }));
}

/** The real API reshapes every error into {error, request_id} -- see
 * app/main.py's http_exception_handler -- and lib/api.ts reads
 * `data.error`. A fixture that answers {detail} silently drops the
 * user-facing message from an abuse-gate 429, which is exactly the text
 * the card is supposed to show. */
function sendError(res, status, message) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ error: message, request_id: "fixture" }));
}

if (MODE === "landing") Object.assign(ROUTES, LANDING_ROUTES);

function sendJson(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);

  if (MODE === "landing" && req.method === "POST" && url.pathname === "/demo/certificate-batch") {
    let raw = "";
    req.on("data", (chunk) => {
      raw += chunk;
    });
    req.on("end", () => {
      let batchId;
      try {
        batchId = JSON.parse(raw).batch_id;
      } catch {
        return sendError(res, 400, "batch_id is required");
      }
      const batch = DEMO_BATCHES.find((b) => b.batch_id === batchId);
      if (!batch) return sendError(res, 404, `unknown batch ${batchId}`);
      // The real API's abuse gates return 429 with a user-facing detail
      // string the card shows verbatim; a reserved batch id exercises
      // that path without a cooldown clock in the fixture.
      if (batchId === "BATCH-PWP-05-COOLDOWN" || url.searchParams.get("gate") === "cooldown") {
        return sendError(res, 429, "cooldown active — try again in 47s");
      }
      const runId = `run-${++runSeq}`;
      runs.set(runId, {
        batchId,
        processorId: batch.processor_id,
        scenario: BATCH_SCENARIO[batchId] ?? "done",
        startedAt: Date.now(),
      });
      return sendJson(res, 202, { meta: META, run_id: runId, batch_id: batchId, processor_id: batch.processor_id });
    });
    return;
  }

  if (MODE === "landing" && url.pathname.startsWith("/runs/")) {
    const body = runResponse(decodeURIComponent(url.pathname.slice("/runs/".length)));
    if (!body) return notFound(res);
    return sendJson(res, 200, body);
  }

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
