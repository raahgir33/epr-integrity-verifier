import type { EvalMetricRow } from "@/lib/api";
import { formatPercentPrecise } from "@/lib/format";

/** docs/DATA_SPEC.md §5's planted issue types, by PLAIN NAME only. The
 * F/H taxonomy codes are internal and must never appear anywhere a
 * visitor can see them — same rule the agent prompts and memos follow. */
const ISSUE_NAMES: Record<string, string> = {
  F1: "Capacity Inflation",
  F2: "Phantom Inbound",
  F3: "Quantity Inflation",
  F4: "Double Use",
  F5: "Ghost Site",
  F6: "Consent Breach",
  F7: "Energy Implausibility",
};

/** F8 and F9 together: the two patterns with no deterministic check
 * behind either, found only by the agents. */
const AGENT_ONLY_NAME = "Agent-Only Patterns";

const STAGE_NAMES: Record<string, string> = {
  checks_only: "Rule Checks",
  full: "Agent Validation",
};

/** app/eval/evaluate.py's describe_misses builds each miss line itself,
 * prefixed with its own code-carrying label ("F5 ghost site: detected
 * 0/1 …"), and that module is frozen at eval-freeze — so the codes are
 * stripped here, on display, by matching the prefixes it actually
 * emits. Order matters only in that each prefix is tried in turn; they
 * are mutually exclusive in practice. */
const MISS_PREFIXES: Record<string, string> = {
  F1: "F1 capacity inflation",
  F2: "F2 phantom inbound",
  F3: "F3 quantity inflation",
  F4: "F4 double use",
  F5: "F5 ghost site",
  F6: "F6 consent breach",
  F7: "F7 energy implausibility",
  AGENT: "F8/F9 (agent-only, no deterministic check)",
};

function missPrefixName(code: string): string {
  return code === "AGENT" ? AGENT_ONLY_NAME : ISSUE_NAMES[code];
}

/** describe_misses also names the two pipeline stages in its own older
 * wording ("Risk band (checks only, …)"); the UI calls them Rule Checks
 * and Agent Validation everywhere else, so those are normalised here
 * alongside the codes. */
const MISS_WORDING: readonly (readonly [string, string])[] = [
  ["(checks only,", `(${STAGE_NAMES.checks_only},`],
  ["(checks + agents,", `(${STAGE_NAMES.full},`],
  // Same reason as the risk-band card's own sub-line: "ground-truth
  // band" sitting next to "extracted facts" reads like a contradiction,
  // when the band compared against is the true one in both modes.
  ["matched the ground-truth band", "matched the true risk band"],
];

/** Rewrites describe_misses' code-carrying label at the start of a miss
 * line to its plain name and normalises its stage wording, leaving the
 * rest of the sentence as the API wrote it. An unrecognised line is
 * returned untouched. */
function rewriteMiss(miss: string): string {
  let line = miss;
  for (const [code, prefix] of Object.entries(MISS_PREFIXES)) {
    if (line.startsWith(prefix)) {
      line = `${missPrefixName(code)}${line.slice(prefix.length)}`;
      break;
    }
  }
  for (const [from, to] of MISS_WORDING) line = line.replace(from, to);
  return line;
}

const TRUTH = "truth";
const EXTRACTED = "extracted";

function factsSourceSuffix(rest: string): [string, string] {
  for (const factsSource of [EXTRACTED, TRUTH]) {
    const suffix = `_${factsSource}`;
    if (rest.endsWith(suffix)) return [rest.slice(0, -suffix.length), factsSource];
  }
  return [rest, ""];
}

function factsSourceLabel(factsSource: string): string {
  return factsSource === EXTRACTED ? "extracted facts" : "ground-truth facts";
}

/** The same thing as a sub-line suffix: "(EXTRACTED FACTS)". Sub-lines
 * are not uppercased by CSS the way StatCard's label is, so the basis is
 * spelled out in caps here to keep it visually distinct from the
 * title-cased words around it. */
function factsSourceSuffixLabel(factsSource: string): string {
  return `(${factsSourceLabel(factsSource).toUpperCase()})`;
}

function stageLabel(stage: string): string {
  return STAGE_NAMES[stage] ?? stage;
}

function findRow(rows: EvalMetricRow[], metric: string): EvalMetricRow | undefined {
  return rows.find((r) => r.metric === metric);
}

export type DisplayMetric = {
  metric: string;
  group: string;
  label: string;
  display: string;
  sub: string;
};

/** Every number shown on /evaluation is one eval_metrics row's own
 * numerator/denominator/value (app/store/cache.py's EvalMetricRow) —
 * this function only chooses a human label and a display format, never
 * computes or adjusts the number itself.
 *
 * Returns null for a metric name it does not recognise, so the page
 * silently ignores an unknown row (e.g. the stale
 * agent_run_to_run_agreement row left behind by T14b's rename) instead
 * of rendering its raw key as a label. `rows` is the metric's own
 * dataset_label siblings, used only to read a companion row's stored
 * number — never to recompute anything. */
export function describeMetric(row: EvalMetricRow, rows: EvalMetricRow[] = []): DisplayMetric | null {
  const { metric, numerator, denominator, value } = row;
  const pct = value !== null ? formatPercentPrecise(value) : "n/a";
  const ratioSub = `${numerator}/${denominator}`;

  // Rendered as a summary figure (summaryFigures below) and nowhere
  // else: a detail card for it would carry the identical value and
  // sub-line, which read as a bug rather than a recap.
  if (metric === "key_field_read_accuracy") return null;

  if (metric.startsWith("issue_recall_")) {
    const [issueCode, factsSource] = factsSourceSuffix(metric.slice("issue_recall_".length));
    const name = ISSUE_NAMES[issueCode];
    if (!name) return null;
    return {
      metric,
      group: "Pattern detection (rule checks)",
      label: `${name} — ${factsSourceLabel(factsSource)}`,
      display: pct,
      sub: `${ratioSub} Planted Instances Detected`,
    };
  }

  if (metric.startsWith("finding_precision_checks_")) {
    const factsSource = metric.slice("finding_precision_checks_".length);
    return {
      metric,
      group: "Finding precision",
      label: `Rule-check finding precision — ${factsSourceLabel(factsSource)}`,
      display: pct,
      sub: `${ratioSub} Failed Checks Matched a Planted Issue`,
    };
  }

  if (metric.startsWith("agent_citation_recall_")) {
    const factsSource = metric.slice("agent_citation_recall_".length);
    return {
      metric,
      group: "Pattern detection (agents)",
      label: `${AGENT_ONLY_NAME} recall — ${factsSourceLabel(factsSource)}`,
      display: pct,
      sub: `${ratioSub} Planted Shipments Cited`,
    };
  }

  if (metric.startsWith("agent_citation_precision_")) {
    const factsSource = metric.slice("agent_citation_precision_".length);
    // The "did not change any tonnage" note is only appended when this
    // dataset's own full-stage tonnage-error row actually reads zero —
    // asserted from stored data, never hardcoded prose.
    const tonnageError = findRow(rows, `unverifiable_t_pct_error_full_${factsSource}`);
    const extraCitations = denominator > numerator;
    const tonnageExact =
      extraCitations && tonnageError !== undefined && tonnageError.numerator === 0;
    return {
      metric,
      group: "Finding precision",
      label: `Agent citation precision (shipments cited) — ${factsSourceLabel(factsSource)}`,
      display: pct,
      sub: tonnageExact
        ? `${ratioSub} Cited Shipments Were Planted. Extra Citations Did Not Change Any Tonnage (Error 0%).`
        : `${ratioSub} Cited Shipments Were Planted`,
    };
  }

  if (metric.startsWith("false_flags_clean_processors_")) {
    const factsSource = metric.slice("false_flags_clean_processors_".length);
    return {
      metric,
      group: "False flags",
      label: `Clean processors wrongly flagged — ${factsSourceLabel(factsSource)}`,
      display: ratioSub,
      sub: pct,
    };
  }

  if (metric.startsWith("false_flags_hard_negatives_")) {
    const factsSource = metric.slice("false_flags_hard_negatives_".length);
    return {
      metric,
      group: "False flags",
      label: `Hard-negative processors wrongly flagged — ${factsSourceLabel(factsSource)}`,
      display: ratioSub,
      sub: pct,
    };
  }

  if (metric.startsWith("risk_band_accuracy_")) {
    const [stage, factsSource] = factsSourceSuffix(metric.slice("risk_band_accuracy_".length));
    return {
      metric,
      group: "Risk-band accuracy",
      label: `${stageLabel(stage)} — ${factsSourceLabel(factsSource)}`,
      display: pct,
      // "Ground-truth band" alongside an "extracted facts" label read as
      // a contradiction. It never was one — risk_band_accuracy compares
      // the assessed band against the band ground truth implies in BOTH
      // modes; the facts source only changes what the system read to
      // reach its own band. Worded so that is unambiguous either way.
      sub: `${ratioSub} Processors Matched the True Risk Band`,
    };
  }

  // Paired into the percentage card below, which reads this row's own
  // stored kilograms for its sub-line — never shown as a card of its own.
  if (metric.startsWith("unverifiable_t_abs_error_kg_")) return null;

  if (metric.startsWith("unverifiable_t_pct_error_")) {
    const [stage, factsSource] = factsSourceSuffix(
      metric.slice("unverifiable_t_pct_error_".length)
    );
    const abs = findRow(rows, `unverifiable_t_abs_error_kg_${stage}_${factsSource}`);
    const processors = findRow(rows, `risk_band_accuracy_${stage}_${factsSource}`)?.denominator;
    const across = processors ? `, Across ${processors} Processors` : "";
    return {
      metric,
      group: "Tonnage error",
      label: `Tonnage error (share of true verifiable tonnes) — ${stageLabel(stage)} — ${factsSourceLabel(factsSource)}`,
      display: pct,
      sub:
        abs !== undefined
          ? `${(abs.numerator / 1000).toFixed(3)} t Mean Absolute Error per Processor${across}`
          : `Mean Absolute Error / True Verifiable Tonnes${across}`,
    };
  }

  if (metric === "finding_set_agreement") {
    return {
      metric,
      group: "Stability, cost and latency",
      label: "Run-to-run finding-set agreement (3 independent extracted-facts runs)",
      display: pct,
      sub: `Pooled Jaccard, ${ratioSub}`,
    };
  }

  if (metric === "risk_band_stability") {
    return {
      metric,
      group: "Stability, cost and latency",
      label: "Risk-band stability (3 independent extracted-facts runs)",
      display: pct,
      sub: `Identical Band Every Run, ${ratioSub} Processors`,
    };
  }

  if (metric === "unverifiable_t_stability") {
    return {
      metric,
      group: "Stability, cost and latency",
      label: "Unverifiable-tonnes stability (3 independent extracted-facts runs)",
      display: pct,
      sub: `Within 0.01t Every Run, ${ratioSub} Processors`,
    };
  }

  if (metric.startsWith("issue_surfaced_as_review_flag_")) {
    const issueCode = metric.slice("issue_surfaced_as_review_flag_".length);
    const name = ISSUE_NAMES[issueCode];
    if (!name) return null;
    return {
      metric,
      group: "Missed-pattern visibility",
      label: `${name}, when missed by its rule check — surfaced as a review flag`,
      display: pct,
      sub: `Of This Pattern's Misses, ${ratioSub}`,
    };
  }

  if (metric === "agent_cost_micro_usd_per_processor") {
    return {
      metric,
      group: "Stability, cost and latency",
      label: "Mean agent cost per processor-run",
      display: `$${(numerator / 1_000_000).toFixed(2)}`,
      sub: "Gemini Cost, Extracted-Facts Stability Runs",
    };
  }

  if (metric === "agent_latency_ms_per_processor") {
    return {
      metric,
      group: "Stability, cost and latency",
      label: "Mean agent latency per processor-run",
      display: `${(numerator / 1000).toFixed(1)} s`,
      sub: "Summed Gemini Call Latency, Extracted-Facts Stability Runs",
    };
  }

  return null;
}

/** describe_misses (app/eval/evaluate.py) writes each miss as a plain
 * string, keyed to the issue label at its start — no structured code to
 * join against. This rewrites that label to its plain name (stripping
 * the F/H code, which must never reach the UI) and, for a missed
 * Ghost-site/Energy-implausibility pattern specifically, appends whether
 * it at least surfaced as a review flag (docs/DATA_SPEC.md §4a), read
 * from this same response's own issue_surfaced_as_review_flag_<code>
 * row. Leaves the rest of every miss line untouched. */
export function annotateMisses(misses: string[], rows: EvalMetricRow[]): string[] {
  return misses.map((miss) => {
    const line = rewriteMiss(miss);

    for (const issueCode of ["F5", "F7"] as const) {
      if (!miss.startsWith(MISS_PREFIXES[issueCode])) continue;
      const row = findRow(rows, `issue_surfaced_as_review_flag_${issueCode}`);
      if (!row || row.denominator === 0) continue;
      return row.numerator === row.denominator
        ? `${line} Surfaced as a review flag.`
        : `${line} Surfaced as a review flag in ${row.numerator}/${row.denominator} miss(es).`;
    }
    return line;
  });
}

/** How many planted patterns the system found, counted two ways from the
 * issue_recall_*_extracted rows and the agent-only citation-recall row —
 * both derived, neither stored as its own metric:
 *
 *  - TYPES: one per pattern kind. Seven rule-check types plus the
 *    agent-only pair as one, so 8 for a dataset carrying all of them.
 *  - INSTANCES: each row's own denominator, i.e. how many processors had
 *    that pattern planted (Capacity inflation is planted twice), plus the
 *    agent-only row's planted-shipment count.
 *
 * Returns null when the dataset has no issue_recall rows at all. */
export type PatternCoverage = {
  typesDetected: number;
  typesTotal: number;
  instancesDetected: number;
  instancesTotal: number;
  missed: string[];
};

export function patternCoverage(rows: EvalMetricRow[]): PatternCoverage | null {
  const recallRows = rows.filter(
    (r) =>
      r.metric.startsWith("issue_recall_") &&
      r.metric.endsWith(`_${EXTRACTED}`) &&
      ISSUE_NAMES[factsSourceSuffix(r.metric.slice("issue_recall_".length))[0]] !== undefined
  );
  if (recallRows.length === 0) return null;

  let typesDetected = 0;
  let typesTotal = 0;
  let instancesDetected = 0;
  let instancesTotal = 0;
  const missed: string[] = [];

  for (const r of recallRows) {
    const [issueCode] = factsSourceSuffix(r.metric.slice("issue_recall_".length));
    typesTotal += 1;
    instancesDetected += r.numerator;
    instancesTotal += r.denominator;
    if (r.denominator > 0 && r.numerator === r.denominator) typesDetected += 1;
    else missed.push(ISSUE_NAMES[issueCode]);
  }

  const agentRecall = findRow(rows, `agent_citation_recall_${EXTRACTED}`);
  if (agentRecall) {
    typesTotal += 1;
    instancesDetected += agentRecall.numerator;
    instancesTotal += agentRecall.denominator;
    if (agentRecall.denominator > 0 && agentRecall.numerator === agentRecall.denominator)
      typesDetected += 1;
    else missed.push(AGENT_ONLY_NAME);
  }

  return { typesDetected, typesTotal, instancesDetected, instancesTotal, missed };
}

export type SummaryFigure = { key: string; label: string; display: string; sub: string };

/** Prefers the ground-truth-facts row (the basis docs/ARCHITECTURE.md's
 * evaluation section quotes) and falls back to extracted facts, so a
 * dataset_label missing one source still shows the figure and says which
 * basis it used rather than printing "n/a". */
function preferredSource(
  rows: EvalMetricRow[],
  build: (factsSource: string) => string
): { row: EvalMetricRow; factsSource: string } | null {
  for (const factsSource of [TRUTH, EXTRACTED]) {
    const row = findRow(rows, build(factsSource));
    if (row && row.value !== null) return { row, factsSource };
  }
  return null;
}

/** /evaluation's four headline figures. Every one reads stored
 * eval_metrics rows (or, for pattern coverage, aggregates their own
 * numerators and denominators) — nothing here is hardcoded, and a figure
 * whose rows are absent is omitted rather than guessed. */
export function summaryFigures(rows: EvalMetricRow[]): SummaryFigure[] {
  const figures: SummaryFigure[] = [];

  const band = preferredSource(rows, (s) => `risk_band_accuracy_checks_only_${s}`);
  const bandFull = band ? findRow(rows, `risk_band_accuracy_full_${band.factsSource}`) : undefined;
  if (band && bandFull?.value != null) {
    figures.push({
      key: "risk_band_accuracy",
      label: "Risk-band accuracy",
      display: `${formatPercentPrecise(band.row.value!)} → ${formatPercentPrecise(bandFull.value)}`,
      sub: `Rule Checks → Agent Validation ${factsSourceSuffixLabel(band.factsSource)}`,
    });
  }

  const err = preferredSource(rows, (s) => `unverifiable_t_pct_error_checks_only_${s}`);
  const errFull = err
    ? findRow(rows, `unverifiable_t_pct_error_full_${err.factsSource}`)
    : undefined;
  if (err && errFull?.value != null) {
    figures.push({
      key: "unverifiable_t_pct_error",
      label: "Tonnage error",
      display: `${formatPercentPrecise(err.row.value!)} → ${formatPercentPrecise(errFull.value)}`,
      sub: `Share of True Verifiable Tonnes ${factsSourceSuffixLabel(err.factsSource)}`,
    });
  }

  const fields = findRow(rows, "key_field_read_accuracy");
  if (fields?.value != null) {
    figures.push({
      key: "key_field_read_accuracy",
      label: "Key fields read correctly",
      display: formatPercentPrecise(fields.value),
      sub: `${fields.numerator.toLocaleString("en-IN")}/${fields.denominator.toLocaleString("en-IN")} Key Fields`,
    });
  }

  const coverage = patternCoverage(rows);
  if (coverage) {
    const missed = coverage.missed.length > 0 ? ` · Missed: ${coverage.missed.join(", ")}` : "";
    figures.push({
      key: "patterns_detected",
      label: "Patterns detected",
      display: `${coverage.typesDetected}/${coverage.typesTotal} Issue Types Detected`,
      sub: `${coverage.instancesDetected} of ${coverage.instancesTotal} Planted Instances Detected${missed}`,
    });
  }

  return figures;
}

export function groupMetrics(rows: EvalMetricRow[]): { group: string; metrics: DisplayMetric[] }[] {
  const described = rows
    .map((row) => describeMetric(row, rows))
    .filter((m): m is DisplayMetric => m !== null);
  const order = [
    "Risk-band accuracy",
    "Tonnage error",
    "Stability, cost and latency",
    "Pattern detection (rule checks)",
    "Pattern detection (agents)",
    "Missed-pattern visibility",
    "Finding precision",
    "False flags",
  ];
  return order
    .map((group) => ({ group, metrics: described.filter((m) => m.group === group) }))
    .filter((g) => g.metrics.length > 0);
}
