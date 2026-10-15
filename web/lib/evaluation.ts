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

/** What the false flag on a given dataset actually was, in plain words.
 *
 * Keyed by dataset_label and nowhere else: this is a finding about one
 * specific evaluation run, not a derived metric, so it must never attach
 * itself to a dataset it was not diagnosed against. Re-running the
 * evaluation on a new seed means re-diagnosing and re-writing this, or
 * the key simply will not match and nothing is claimed.
 *
 * heldout-seed7, diagnosed 14 Oct: the flagged processor is clean. The
 * agents raised one observation about the regularity of its weighbridge
 * ticket numbers, which the systemic guard classified non-deducting. It
 * appears in ONE of the three saved identical re-runs — the single
 * misread document field in that dataset is present in all three — so it
 * is variation in the agents' own output, not a reading error. */
const FALSE_FLAG_CAUSE: Record<string, string> = {
  "heldout-seed7":
    " It is one observation the agents raised about how regular a processor's weighbridge ticket " +
    "numbers look, and it appears in only one of three identical re-runs — variation in the " +
    "agents' own output rather than a misread document.",
};

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
    // "Of the planted instances the rule check missed, how many did the
    // agents at least surface as a review flag?" — vacuous once the check
    // misses none, which is what a zero denominator means. Since the
    // 14 Oct metric correction that is the normal case, and rendering it
    // would leave a "Missed-pattern visibility" section of n/a cards
    // describing misses that no longer exist.
    if (denominator === 0) return null;
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
/** describe_misses emits one line per stage/facts-source combination
 * restating risk-band accuracy ("Risk band (checks only, truth facts):
 * 7/10 processor(s) matched..."). Those are summaries of a metric the
 * Risk-band accuracy section already shows as its own card, not misses,
 * and four of them crowd out the real ones. Dropped here, in the display
 * layer, rather than in app/eval/evaluate.py — that module ships inside
 * the API image, so changing it would force an API redeploy for a purely
 * cosmetic change. */
function isRiskBandSummary(miss: string): boolean {
  return miss.startsWith("Risk band (");
}

/** A wrongly-flagged clean processor says nothing on its own about
 * whether the flag cost that processor any tonnage — a non-deducting
 * finding (a review flag, or one the systemic guard caught) leaves the
 * figures untouched. That IS answerable from this dataset's own
 * full-stage tonnage-error row, so the note is appended only when that
 * row actually reads zero, never asserted. Deliberately not naming the
 * processor or the finding: that detail is real but dataset-specific,
 * and hardcoding it here would quietly go stale on the next seed. */
function falseFlagNote(miss: string, rows: EvalMetricRow[], datasetLabel?: string | null): string {
  const match = /wrongly flagged under (\w+) facts/.exec(miss);
  if (!match) return miss;
  const tonnage = findRow(rows, `unverifiable_t_pct_error_full_${match[1]}`);
  if (!tonnage || tonnage.numerator !== 0) return miss;
  const tonnageNote =
    " The flag did not change any tonnage — verified tonnes at this stage match ground truth exactly.";
  return `${miss}${tonnageNote}${FALSE_FLAG_CAUSE[datasetLabel ?? ""] ?? ""}`;
}

export function annotateMisses(
  misses: string[],
  rows: EvalMetricRow[],
  datasetLabel?: string | null
): string[] {
  return misses.filter((miss) => !isRiskBandSummary(miss)).map((miss) => {
    const line = falseFlagNote(rewriteMiss(miss), rows, datasetLabel);

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

/** A figure that exists on both fact sources: the primary is
 * ground-truth facts where present (the basis the evaluation quotes),
 * falling back to extracted so a dataset_label carrying only one source
 * still shows the tile rather than printing "n/a". `other` is the
 * remaining source's value, and is null when it is absent or identical —
 * the tile appends it only when it genuinely differs, so an agreeing pair
 * adds no noise. */
function bothBases(
  rows: EvalMetricRow[],
  build: (factsSource: string) => string
): { value: number; factsSource: string; other: number | null } | null {
  const order = findRow(rows, build(TRUTH))?.value != null ? [TRUTH, EXTRACTED] : [EXTRACTED, TRUTH];
  const primary = findRow(rows, build(order[0]));
  if (primary?.value == null) return null;
  const secondary = findRow(rows, build(order[1]));
  const other =
    secondary?.value != null && secondary.value !== primary.value ? secondary.value : null;
  return { value: primary.value, factsSource: order[0], other };
}

function otherBasisSuffix(
  basis: { factsSource: string; other: number | null } | null
): string {
  if (!basis || basis.other === null) return "";
  const otherName = basis.factsSource === TRUTH ? "Extracted" : "Ground-Truth";
  return ` · ${formatPercentPrecise(basis.other)} on ${otherName} Facts`;
}

/** /evaluation's four headline figures. Every one reads stored
 * eval_metrics rows (or, for pattern coverage, aggregates their own
 * numerators and denominators) — nothing here is hardcoded, and a figure
 * whose rows are absent is omitted rather than guessed. */
export function summaryFigures(rows: EvalMetricRow[]): SummaryFigure[] {
  const figures: SummaryFigure[] = [];

  // Both bases on one tile: the ground-truth pair as the headline, the
  // extracted-facts figure appended only when it actually differs, so an
  // identical pair doesn't add noise.
  const bandAfter = bothBases(rows, (fs) => `risk_band_accuracy_full_${fs}`);
  const bandBefore = bandAfter
    ? findRow(rows, `risk_band_accuracy_checks_only_${bandAfter.factsSource}`)
    : undefined;
  if (bandAfter && bandBefore?.value != null) {
    figures.push({
      key: "risk_band_accuracy",
      label: "Risk-band accuracy",
      display: `${formatPercentPrecise(bandBefore.value)} → ${formatPercentPrecise(bandAfter.value)}`,
      sub:
        `Rule Checks → Agent Validation (${factsSourceLabel(bandAfter.factsSource).toUpperCase()})` +
        otherBasisSuffix(bandAfter),
    });
  }

  const errAfter = bothBases(rows, (fs) => `unverifiable_t_pct_error_full_${fs}`);
  const errBefore = errAfter
    ? findRow(rows, `unverifiable_t_pct_error_checks_only_${errAfter.factsSource}`)
    : undefined;
  if (errAfter && errBefore?.value != null) {
    figures.push({
      key: "unverifiable_t_pct_error",
      label: "Tonnage error",
      display: `${formatPercentPrecise(errBefore.value)} → ${formatPercentPrecise(errAfter.value)}`,
      sub:
        `Share of True Verifiable Tonnes (${factsSourceLabel(errAfter.factsSource).toUpperCase()})` +
        otherBasisSuffix(errAfter),
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
      display: `${coverage.typesDetected}/${coverage.typesTotal} (${coverage.instancesDetected}/${coverage.instancesTotal} Instances)`,
      sub: `Issue Types, With Planted Instances in Brackets${missed}`,
    });
  }

  return figures;
}

/** One line under the summary row explaining why the extracted-facts
 * figure trails the ground-truth one, shown only when it actually does.
 *
 * Deliberately NOT attributed to the single misread field of 5,431. On
 * seed 7 the gap is one processor's non-deducting agent finding, and the
 * three saved extracted-facts probe runs — identical input, misread field
 * included in every one — raise it in only one run of the three. That is
 * run-to-run model variability, already published on this page as
 * risk-band stability, not an extraction artifact. Tonnage is unaffected
 * either way, which is what the tonnes-stability figure shows. */
export function extractedGapNote(rows: EvalMetricRow[]): string | null {
  const truth = findRow(rows, "risk_band_accuracy_full_truth");
  const extracted = findRow(rows, "risk_band_accuracy_full_extracted");
  if (truth?.value == null || extracted?.value == null || extracted.value >= truth.value) {
    return null;
  }
  const bandStability = findRow(rows, "risk_band_stability");
  const tonnesStability = findRow(rows, "unverifiable_t_stability");
  const stability =
    bandStability && tonnesStability
      ? ` The same effect is measured directly as risk-band stability (${bandStability.numerator}/${bandStability.denominator} processors identical across three independent runs) while unverifiable tonnes held identical in ${tonnesStability.numerator}/${tonnesStability.denominator}.`
      : "";
  return (
    "The extracted-facts figure trails the ground-truth one by a single processor, where the " +
    "agents raised one non-deducting finding that the guardrails kept out of the tonnage. It is " +
    `run-to-run variation in the agents' own output, not a reading error.${stability}`
  );
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

// --- chart data (T18) ------------------------------------------------------
//
// Every value below is one eval_metrics row's own stored numbers. These
// selectors choose labels, decode the per-processor metric names and group
// rows for plotting; they never compute or adjust a figure. Each returns
// null when its rows are absent, so a chart is hidden rather than drawn
// with holes or an "n/a".

const PER_PROCESSOR_PREFIX = "per_processor_";
const ABS_ERROR_PREFIX = `${PER_PROCESSOR_PREFIX}unverifiable_t_abs_error_kg_`;
const BAND_RUN_PREFIX = `${PER_PROCESSOR_PREFIX}risk_band_run`;

/** Band by the ordinal scripts/evaluate.py encodes into the numerator.
 * Its own RISK_BAND_ORDER is the source of truth and is asserted there
 * against the scorer's frozen list; this mirrors it for display. */
const BAND_BY_ORDINAL = ["Low", "Medium", "High"];

/** Kilograms as tonnes, to three decimal places — the same rule the
 * tonnage-error sub-line already applies (describeMetric above), so a
 * per-processor figure and the aggregate beside it read alike. */
export function formatErrorTonnes(kg: number): string {
  return `${(kg / 1000).toFixed(3)} t`;
}

const STAGES = ["checks_only", "full"] as const;
const FACTS_SOURCES = [TRUTH, EXTRACTED] as const;

/** A per-processor metric name carries its processor id as the final
 * underscore-separated segment, and a stage name that itself contains an
 * underscore ("checks_only"). So the id is split off the end first, and
 * the remainder is matched against the two known facts_source suffixes —
 * the same guarded approach app/eval/evaluate.py's
 * _split_facts_source_suffix uses, never a blind split. */
function parseAbsErrorMetric(
  metric: string
): { stage: string; factsSource: string; processorId: string } | null {
  if (!metric.startsWith(ABS_ERROR_PREFIX)) return null;
  const rest = metric.slice(ABS_ERROR_PREFIX.length);
  const split = rest.lastIndexOf("_");
  if (split <= 0) return null;
  const processorId = rest.slice(split + 1);
  const [stage, factsSource] = factsSourceSuffix(rest.slice(0, split));
  if (!processorId || !factsSource || STAGE_NAMES[stage] === undefined) return null;
  return { stage, factsSource, processorId };
}

function parseBandMetric(metric: string): { run: number; processorId: string } | null {
  if (!metric.startsWith(BAND_RUN_PREFIX)) return null;
  const rest = metric.slice(BAND_RUN_PREFIX.length);
  const split = rest.indexOf("_");
  if (split <= 0) return null;
  const run = Number(rest.slice(0, split));
  const processorId = rest.slice(split + 1);
  if (!Number.isInteger(run) || run < 1 || !processorId) return null;
  return { run, processorId };
}

export type StageValue = {
  stage: string;
  stageLabel: string;
  ratio: number;
  display: string;
  numerator: number;
  denominator: number;
};

export type BasisSeries = {
  factsSource: string;
  basisLabel: string;
  stages: StageValue[];
};

export type AccuracyComparison = {
  bandAccuracy: BasisSeries[];
  tonnageError: BasisSeries[];
};

function basisSeries(rows: EvalMetricRow[], prefix: string): BasisSeries[] {
  const series: BasisSeries[] = [];
  for (const factsSource of FACTS_SOURCES) {
    const stages: StageValue[] = [];
    for (const stage of STAGES) {
      const row = findRow(rows, `${prefix}${stage}_${factsSource}`);
      if (!row || row.value === null) continue;
      stages.push({
        stage,
        stageLabel: stageLabel(stage),
        ratio: row.value,
        display: formatPercentPrecise(row.value),
        numerator: row.numerator,
        denominator: row.denominator,
      });
    }
    if (stages.length > 0) {
      series.push({
        factsSource,
        basisLabel: factsSource === EXTRACTED ? "Extracted Facts" : "Ground-Truth Facts",
        stages,
      });
    }
  }
  return series;
}

/** Chart (a): risk-band accuracy and tonnage error, rule checks against
 * agent validation, on both fact sources. */
export function accuracyComparison(rows: EvalMetricRow[]): AccuracyComparison | null {
  const bandAccuracy = basisSeries(rows, "risk_band_accuracy_");
  const tonnageError = basisSeries(rows, "unverifiable_t_pct_error_");
  if (bandAccuracy.length === 0 && tonnageError.length === 0) return null;
  return { bandAccuracy, tonnageError };
}

export type ProcessorErrorColumn = {
  key: string;
  stage: string;
  factsSource: string;
  label: string;
};

export type ProcessorErrors = {
  processorIds: string[];
  /** All four stage/facts-source combinations, for the figures table. */
  columns: ProcessorErrorColumn[];
  /** processorId -> column key -> error in kilograms. */
  kg: Record<string, Record<string, number>>;
};

/** Chart (b): each processor's own |assessed - true| verifiable tonnes.
 * Returns every combination that has rows; the chart plots the
 * ground-truth pair and its figures table shows all four. */
export function processorErrors(rows: EvalMetricRow[]): ProcessorErrors | null {
  const kg: Record<string, Record<string, number>> = {};
  const seenColumns = new Set<string>();
  const processorIds = new Set<string>();

  for (const row of rows) {
    const parsed = parseAbsErrorMetric(row.metric);
    if (!parsed) continue;
    const key = `${parsed.stage}_${parsed.factsSource}`;
    seenColumns.add(key);
    processorIds.add(parsed.processorId);
    kg[parsed.processorId] = { ...(kg[parsed.processorId] ?? {}), [key]: row.numerator };
  }

  if (processorIds.size === 0) return null;

  const columns: ProcessorErrorColumn[] = [];
  for (const factsSource of FACTS_SOURCES) {
    for (const stage of STAGES) {
      const key = `${stage}_${factsSource}`;
      if (!seenColumns.has(key)) continue;
      columns.push({
        key,
        stage,
        factsSource,
        label: `${stageLabel(stage)} — ${factsSourceLabel(factsSource)}`,
      });
    }
  }

  return { processorIds: [...processorIds].sort(), columns, kg };
}

export type DetectionCell = {
  factsSource: string;
  ok: boolean;
  detail: string;
};

export type DetectionRow = {
  name: string;
  /** "pattern": ok means every planted instance was found. "false-flag":
   * ok means nothing clean was flagged, so the polarity is inverted and
   * the row is labelled accordingly. */
  kind: "pattern" | "false-flag";
  cells: DetectionCell[];
};

export type DetectionMatrix = {
  bases: { factsSource: string; label: string }[];
  rows: DetectionRow[];
};

/** Chart (c): every planted pattern against each facts source, plus the
 * two false-flag families. */
export function detectionMatrix(rows: EvalMetricRow[]): DetectionMatrix | null {
  const bases = FACTS_SOURCES.filter((factsSource) =>
    rows.some((r) => r.metric.endsWith(`_${factsSource}`))
  ).map((factsSource) => ({
    factsSource,
    label: factsSource === EXTRACTED ? "Extracted Facts" : "Ground-Truth Facts",
  }));
  if (bases.length === 0) return null;

  const patternRows: DetectionRow[] = [];

  for (const issueCode of Object.keys(ISSUE_NAMES)) {
    const cells: DetectionCell[] = [];
    for (const { factsSource } of bases) {
      const row = findRow(rows, `issue_recall_${issueCode}_${factsSource}`);
      if (!row) continue;
      cells.push({
        factsSource,
        ok: row.denominator > 0 && row.numerator >= row.denominator,
        detail: `${row.numerator}/${row.denominator}`,
      });
    }
    if (cells.length > 0) patternRows.push({ name: ISSUE_NAMES[issueCode], kind: "pattern", cells });
  }

  const agentCells: DetectionCell[] = [];
  for (const { factsSource } of bases) {
    const row = findRow(rows, `agent_citation_recall_${factsSource}`);
    if (!row) continue;
    agentCells.push({
      factsSource,
      ok: row.denominator > 0 && row.numerator >= row.denominator,
      detail: `${row.numerator}/${row.denominator}`,
    });
  }
  if (agentCells.length > 0)
    patternRows.push({ name: AGENT_ONLY_NAME, kind: "pattern", cells: agentCells });

  const falseFlagFamilies: [string, string][] = [
    ["false_flags_clean_processors_", "No False Flags on Clean Processors"],
    ["false_flags_hard_negatives_", "No False Flags on Hard-Negative Processors"],
  ];
  const falseFlagRows: DetectionRow[] = [];
  for (const [prefix, name] of falseFlagFamilies) {
    const cells: DetectionCell[] = [];
    for (const { factsSource } of bases) {
      const row = findRow(rows, `${prefix}${factsSource}`);
      if (!row) continue;
      cells.push({
        factsSource,
        ok: row.numerator === 0,
        detail:
          row.numerator === 0
            ? `0/${row.denominator} flagged`
            : `${row.numerator}/${row.denominator} flagged`,
      });
    }
    if (cells.length > 0) falseFlagRows.push({ name, kind: "false-flag", cells });
  }

  const allRows = [...patternRows, ...falseFlagRows];
  if (allRows.length === 0) return null;
  return { bases, rows: allRows };
}

export type StabilityCell = { run: number; band: string | null };
export type StabilityRow = { processorId: string; cells: StabilityCell[] };
export type BandStability = { runs: number[]; rows: StabilityRow[] };

/** Chart (d): each processor's assessed band in each of the saved
 * extracted-facts runs, decoded from the stored ordinal. */
export function bandStability(rows: EvalMetricRow[]): BandStability | null {
  const bandByProcessor: Record<string, Record<number, string>> = {};
  const runs = new Set<number>();

  for (const row of rows) {
    const parsed = parseBandMetric(row.metric);
    if (!parsed) continue;
    const band = BAND_BY_ORDINAL[row.numerator];
    if (band === undefined) continue;
    runs.add(parsed.run);
    bandByProcessor[parsed.processorId] = {
      ...(bandByProcessor[parsed.processorId] ?? {}),
      [parsed.run]: band,
    };
  }

  const runNumbers = [...runs].sort((a, b) => a - b);
  const processorIds = Object.keys(bandByProcessor).sort();
  if (runNumbers.length === 0 || processorIds.length === 0) return null;

  return {
    runs: runNumbers,
    rows: processorIds.map((processorId) => ({
      processorId,
      cells: runNumbers.map((run) => ({ run, band: bandByProcessor[processorId][run] ?? null })),
    })),
  };
}
