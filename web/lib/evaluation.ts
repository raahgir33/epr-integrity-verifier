import type { EvalMetricRow } from "@/lib/api";
import { formatPercent } from "@/lib/format";

/** Human labels for docs/DATA_SPEC.md §5's planted issue types — display
 * only, never a measured number itself. */
const ISSUE_LABELS: Record<string, string> = {
  F1: "F1 capacity inflation",
  F2: "F2 phantom inbound",
  F3: "F3 quantity inflation",
  F4: "F4 double use",
  F5: "F5 ghost site",
  F6: "F6 consent breach",
  F7: "F7 energy implausibility",
};

function factsSourceSuffix(rest: string): [string, string] {
  for (const factsSource of ["extracted", "truth"]) {
    const suffix = `_${factsSource}`;
    if (rest.endsWith(suffix)) return [rest.slice(0, -suffix.length), factsSource];
  }
  return [rest, ""];
}

function factsSourceLabel(factsSource: string): string {
  return factsSource === "extracted" ? "extracted facts" : "ground-truth facts";
}

export type DisplayMetric = {
  metric: string;
  group: string;
  label: string;
  display: string;
  sub: string;
};

/** Every number shown here is one eval_metrics row's own numerator/
 * denominator/value (app/store/cache.py's EvalMetricRow) — this function
 * only chooses a human label and a display format, never computes or
 * adjusts the number itself. */
export function describeMetric(row: EvalMetricRow): DisplayMetric {
  const { metric, numerator, denominator, value } = row;
  const pct = value !== null ? formatPercent(value) : "n/a";
  const ratioSub = `${numerator}/${denominator}`;

  if (metric === "key_field_read_accuracy") {
    return { metric, group: "Extraction", label: "Key-field extraction accuracy", display: pct, sub: ratioSub };
  }

  if (metric.startsWith("issue_recall_")) {
    const [issueCode, factsSource] = factsSourceSuffix(metric.slice("issue_recall_".length));
    return {
      metric,
      group: "Issue-type recall (rule checks)",
      label: `${ISSUE_LABELS[issueCode] ?? issueCode} — ${factsSourceLabel(factsSource)}`,
      display: pct,
      sub: ratioSub,
    };
  }

  if (metric.startsWith("finding_precision_checks_")) {
    const factsSource = metric.slice("finding_precision_checks_".length);
    return {
      metric,
      group: "Finding precision",
      label: `Rule-check precision — ${factsSourceLabel(factsSource)}`,
      display: pct,
      sub: ratioSub,
    };
  }

  if (metric.startsWith("agent_citation_recall_")) {
    const factsSource = metric.slice("agent_citation_recall_".length);
    return {
      metric,
      group: "Issue-type recall (agents)",
      label: `F8/F9 (agent-only) recall — ${factsSourceLabel(factsSource)}`,
      display: pct,
      sub: ratioSub,
    };
  }

  if (metric.startsWith("agent_citation_precision_")) {
    const factsSource = metric.slice("agent_citation_precision_".length);
    return {
      metric,
      group: "Finding precision",
      label: `F8/F9 (agent-only) precision — ${factsSourceLabel(factsSource)}`,
      display: pct,
      sub: ratioSub,
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
    const stageLabel = stage === "checks_only" ? "checks only" : "checks + agents";
    return {
      metric,
      group: "Risk-band accuracy",
      label: `${stageLabel} — ${factsSourceLabel(factsSource)}`,
      display: pct,
      sub: ratioSub,
    };
  }

  if (metric.startsWith("unverifiable_t_abs_error_kg_")) {
    const [stage, factsSource] = factsSourceSuffix(
      metric.slice("unverifiable_t_abs_error_kg_".length)
    );
    const stageLabel = stage === "checks_only" ? "checks only" : "checks + agents";
    return {
      metric,
      group: "Unverifiable-tonnes error",
      label: `Mean absolute error, ${stageLabel} — ${factsSourceLabel(factsSource)}`,
      display: `${numerator.toLocaleString("en-IN")} kg`,
      sub: "mean |assessed − true| across processors",
    };
  }

  if (metric.startsWith("unverifiable_t_pct_error_")) {
    const [stage, factsSource] = factsSourceSuffix(
      metric.slice("unverifiable_t_pct_error_".length)
    );
    const stageLabel = stage === "checks_only" ? "checks only" : "checks + agents";
    return {
      metric,
      group: "Unverifiable-tonnes error",
      label: `Mean percentage error, ${stageLabel} — ${factsSourceLabel(factsSource)}`,
      display: pct,
      sub: "mean |assessed − true| / true, across processors",
    };
  }

  if (metric === "finding_set_agreement") {
    return {
      metric,
      group: "Stability, cost and latency",
      label: "Run-to-run finding-set agreement (3 independent extracted-facts runs)",
      display: pct,
      sub: `pooled Jaccard, ${ratioSub}`,
    };
  }

  if (metric === "risk_band_stability") {
    return {
      metric,
      group: "Stability, cost and latency",
      label: "Risk-band stability (3 independent extracted-facts runs)",
      display: pct,
      sub: `identical band every run, ${ratioSub} processors`,
    };
  }

  if (metric === "unverifiable_t_stability") {
    return {
      metric,
      group: "Stability, cost and latency",
      label: "Unverifiable-tonnes stability (3 independent extracted-facts runs)",
      display: pct,
      sub: `within 0.01t every run, ${ratioSub} processors`,
    };
  }

  if (metric.startsWith("issue_surfaced_as_review_flag_")) {
    const issueCode = metric.slice("issue_surfaced_as_review_flag_".length);
    return {
      metric,
      group: "Missed-pattern visibility",
      label: `${ISSUE_LABELS[issueCode] ?? issueCode}, when missed by its rule check — surfaced as a review flag`,
      display: pct,
      sub: `of this pattern's misses, ${ratioSub}`,
    };
  }

  if (metric === "agent_cost_micro_usd_per_processor") {
    return {
      metric,
      group: "Stability, cost and latency",
      label: "Mean agent cost per processor-run",
      display: `$${(numerator / 1_000_000).toFixed(4)}`,
      sub: "Gemini cost, extracted-facts stability runs",
    };
  }

  if (metric === "agent_latency_ms_per_processor") {
    return {
      metric,
      group: "Stability, cost and latency",
      label: "Mean agent latency per processor-run",
      display: `${numerator.toLocaleString("en-IN")} ms`,
      sub: "summed Gemini call latency, extracted-facts stability runs",
    };
  }

  return { metric, group: "Other", label: metric, display: pct, sub: ratioSub };
}

/** describe_misses (app/eval/evaluate.py) writes each miss as a plain
 * string, keyed to the issue label at its start — no structured code to
 * join against. For a missed F5/F7 pattern specifically, appends whether
 * it at least surfaced as a review flag (docs/DATA_SPEC.md §4a), read
 * from this same response's own issue_surfaced_as_review_flag_<code>
 * row. Leaves every other miss line untouched. */
export function annotateMisses(misses: string[], rows: EvalMetricRow[]): string[] {
  return misses.map((miss) => {
    for (const issueCode of ["F5", "F7"] as const) {
      if (!miss.startsWith(ISSUE_LABELS[issueCode])) continue;
      const row = rows.find((r) => r.metric === `issue_surfaced_as_review_flag_${issueCode}`);
      if (!row || row.denominator === 0) continue;
      return row.numerator === row.denominator
        ? `${miss} Surfaced as a review flag.`
        : `${miss} Surfaced as a review flag in ${row.numerator}/${row.denominator} miss(es).`;
    }
    return miss;
  });
}

export function groupMetrics(rows: EvalMetricRow[]): { group: string; metrics: DisplayMetric[] }[] {
  const described = rows.map(describeMetric);
  const order = [
    "Risk-band accuracy",
    "Unverifiable-tonnes error",
    "Stability, cost and latency",
    "Extraction",
    "Issue-type recall (rule checks)",
    "Issue-type recall (agents)",
    "Missed-pattern visibility",
    "Finding precision",
    "False flags",
    "Other",
  ];
  return order
    .map((group) => ({ group, metrics: described.filter((m) => m.group === group) }))
    .filter((g) => g.metrics.length > 0);
}
