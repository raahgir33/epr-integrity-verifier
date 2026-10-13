import { describe, expect, it } from "vitest";
import {
  annotateMisses,
  describeMetric,
  extractedGapNote,
  groupMetrics,
  patternCoverage,
  summaryFigures,
} from "./evaluation";
import { formatPercentPrecise } from "./format";
import type { EvalMetricRow } from "./api";

function row(metric: string, numerator: number, denominator: number): EvalMetricRow {
  return {
    metric,
    numerator,
    denominator,
    value: denominator ? numerator / denominator : null,
    computed_at: "2026-10-11T00:00:00Z",
  };
}

/** The real heldout-seed7 rows behind every number on the page, as
 * stored (docs/DATA_SPEC.md §7; verified against ground_truth.json and
 * the saved extracted-facts probe runs). Used so the assertions below
 * are about actual displayed values, not invented ones. */
const HELDOUT: EvalMetricRow[] = [
  row("key_field_read_accuracy", 5430, 5431),
  row("issue_recall_F1_extracted", 2, 2),
  row("issue_recall_F2_extracted", 1, 1),
  row("issue_recall_F3_extracted", 1, 1),
  row("issue_recall_F4_extracted", 1, 1),
  row("issue_recall_F5_extracted", 0, 1),
  row("issue_recall_F6_extracted", 1, 1),
  row("issue_recall_F7_extracted", 0, 1),
  row("agent_citation_recall_extracted", 3, 3),
  row("agent_citation_precision_truth", 3, 3),
  row("agent_citation_precision_extracted", 3, 19),
  row("finding_precision_checks_extracted", 7, 8),
  row("risk_band_accuracy_checks_only_truth", 7, 10),
  row("risk_band_accuracy_full_truth", 9, 10),
  row("risk_band_accuracy_checks_only_extracted", 7, 10),
  row("risk_band_accuracy_full_extracted", 8, 10),
  row("unverifiable_t_abs_error_kg_checks_only_truth", 2247, 1),
  row("unverifiable_t_pct_error_checks_only_truth", 19545, 1_000_000),
  row("unverifiable_t_abs_error_kg_full_truth", 0, 1),
  row("unverifiable_t_pct_error_full_truth", 0, 1_000_000),
  row("unverifiable_t_abs_error_kg_checks_only_extracted", 2247, 1),
  row("unverifiable_t_pct_error_checks_only_extracted", 19545, 1_000_000),
  row("unverifiable_t_abs_error_kg_full_extracted", 0, 1),
  row("unverifiable_t_pct_error_full_extracted", 0, 1_000_000),
  row("risk_band_stability", 9, 10),
  row("unverifiable_t_stability", 10, 10),
  row("agent_cost_micro_usd_per_processor", 290_000, 1),
  row("agent_latency_ms_per_processor", 72_700, 1),
];

function describedIn(rows: EvalMetricRow[], metric: string) {
  const found = rows.find((r) => r.metric === metric)!;
  return describeMetric(found, rows)!;
}

describe("formatPercentPrecise", () => {
  it("truncates instead of rounding, so a near-perfect ratio never reads 100%", () => {
    expect(formatPercentPrecise(5430 / 5431)).toBe("99.98%");
    expect(formatPercentPrecise(5521 / 5523)).toBe("99.96%");
  });

  it("reaches 100% only on exact equality", () => {
    expect(formatPercentPrecise(1)).toBe("100%");
    expect(formatPercentPrecise(0.9999999)).toBe("99.99%");
  });

  it("trims trailing zeros", () => {
    expect(formatPercentPrecise(0.7)).toBe("70%");
    expect(formatPercentPrecise(0.9)).toBe("90%");
    expect(formatPercentPrecise(0.875)).toBe("87.5%");
    expect(formatPercentPrecise(0)).toBe("0%");
  });

  it("keeps the two decimals that matter", () => {
    expect(formatPercentPrecise(0.019545)).toBe("1.95%");
    expect(formatPercentPrecise(3 / 19)).toBe("15.78%");
  });
});

describe("describeMetric", () => {
  it("shows the tonnage error as a percentage with its absolute tonnes and basis", () => {
    const described = describedIn(HELDOUT, "unverifiable_t_pct_error_checks_only_truth");

    expect(described.group).toBe("Tonnage error");
    expect(described.label).toContain("share of true verifiable tonnes");
    expect(described.label).toContain("Rule Checks");
    expect(described.display).toBe("1.95%");
    expect(described.sub).toBe("2.247 t Mean Absolute Error per Processor, Across 10 Processors");
  });

  it("relabels the agents' exact-tonnage card the same way", () => {
    const described = describedIn(HELDOUT, "unverifiable_t_pct_error_full_truth");

    expect(described.label).toContain("share of true verifiable tonnes");
    expect(described.label).toContain("Agent Validation");
    expect(described.display).toBe("0%");
    expect(described.sub).toBe("0.000 t Mean Absolute Error per Processor, Across 10 Processors");
  });

  it("never renders the absolute-kilograms row as a card of its own", () => {
    expect(describeMetric(row("unverifiable_t_abs_error_kg_full_truth", 0, 1), HELDOUT)).toBeNull();
  });

  it("names agent citation precision by what it counts, and says tonnage was unaffected", () => {
    const described = describedIn(HELDOUT, "agent_citation_precision_extracted");

    expect(described.label).toContain("Agent citation precision (shipments cited)");
    expect(described.display).toBe("15.78%");
    expect(described.sub).toContain("3/19 Cited Shipments Were Planted");
    expect(described.sub).toContain("Did Not Change Any Tonnage (Error 0%)");
  });

  it("omits the tonnage note when this dataset's own tonnage error is not zero", () => {
    const rows = [
      row("agent_citation_precision_truth", 3, 3),
  row("agent_citation_precision_extracted", 3, 19),
      row("unverifiable_t_pct_error_full_extracted", 19545, 1_000_000),
    ];
    expect(describedIn(rows, "agent_citation_precision_extracted").sub).not.toContain(
      "Did Not Change Any Tonnage"
    );
  });

  it("uses Rule Checks / Agent Validation for the risk-band stages", () => {
    expect(describedIn(HELDOUT, "risk_band_accuracy_checks_only_truth").label).toContain(
      "Rule Checks"
    );
    expect(describedIn(HELDOUT, "risk_band_accuracy_full_truth").label).toContain(
      "Agent Validation"
    );
  });

  it("formats cost in dollars and latency in seconds", () => {
    expect(describedIn(HELDOUT, "agent_cost_micro_usd_per_processor").display).toBe("$0.29");
    expect(describedIn(HELDOUT, "agent_latency_ms_per_processor").display).toBe("72.7 s");
  });

  it("never pairs a ground-truth-band phrase with an extracted-facts label", () => {
    const described = describedIn(HELDOUT, "risk_band_accuracy_checks_only_extracted");
    expect(described.label).toContain("extracted facts");
    expect(described.sub).toBe("7/10 Processors Matched the True Risk Band");
    expect(described.sub).not.toContain("ground-truth");
  });

  it("renders key-field accuracy only as a summary figure, never as a duplicate card", () => {
    expect(describeMetric(row("key_field_read_accuracy", 5430, 5431), HELDOUT)).toBeNull();
  });

  it("says what the rule-check precision ratio counts", () => {
    expect(describedIn(HELDOUT, "finding_precision_checks_extracted").sub).toBe(
      "7/8 Failed Checks Matched a Planted Issue"
    );
  });

  it("omits the extra-citations note when there were no extra citations", () => {
    const described = describedIn(HELDOUT, "agent_citation_precision_truth");
    expect(described.display).toBe("100%");
    expect(described.sub).toBe("3/3 Cited Shipments Were Planted");
  });

  it("labels the stability metrics", () => {
    expect(describeMetric(row("finding_set_agreement", 8, 10))!.label).toContain(
      "finding-set agreement"
    );
    expect(describeMetric(row("risk_band_stability", 9, 10))!.label).toContain(
      "Risk-band stability"
    );
    expect(describeMetric(row("unverifiable_t_stability", 10, 10))!.label).toContain(
      "Unverifiable-tonnes stability"
    );
  });

  it("labels issue_surfaced_as_review_flag_<code> under its own group, by plain name", () => {
    const described = describeMetric(row("issue_surfaced_as_review_flag_F5", 1, 1))!;
    expect(described.group).toBe("Missed-pattern visibility");
    expect(described.label).toContain("Ghost Site");
  });

  it("hides a review-flag metric with nothing left to be visible about", () => {
    // Zero denominator = the rule check missed no instance of that
    // pattern, so there is no miss for the agents to have surfaced.
    expect(describeMetric(row("issue_surfaced_as_review_flag_F5", 0, 0))).toBeNull();
    expect(describeMetric(row("issue_surfaced_as_review_flag_F5", 1, 1))).not.toBeNull();
  });

  it("ignores an unknown metric name instead of rendering its raw key", () => {
    // The stale row T14b's rename left behind in BigQuery.
    expect(describeMetric(row("agent_run_to_run_agreement", 8, 10))).toBeNull();
    expect(describeMetric(row("issue_recall_F42_extracted", 1, 1))).toBeNull();
  });
});

describe("no internal taxonomy codes reach the page", () => {
  const CODE = /\b[FH][1-9]\b/;

  it("appears in no label or sub-line of any stored metric", () => {
    for (const { metrics } of groupMetrics(HELDOUT)) {
      for (const m of metrics) {
        expect(m.label, m.metric).not.toMatch(CODE);
        expect(m.sub, m.metric).not.toMatch(CODE);
      }
    }
  });

  it("appears in no summary figure", () => {
    for (const f of summaryFigures(HELDOUT)) {
      expect(f.label, f.key).not.toMatch(CODE);
      expect(f.display, f.key).not.toMatch(CODE);
      expect(f.sub, f.key).not.toMatch(CODE);
    }
  });

  it("appears in no miss line, which the API writes with its codes attached", () => {
    const misses = annotateMisses(
      [
        "F5 ghost site: detected 0/1 planted instance(s) under extracted facts.",
        "F7 energy implausibility: detected 0/1 planted instance(s) under extracted facts.",
        "F8/F9 (agent-only, no deterministic check): recalled 2/3 true shipment citation(s) under extracted facts.",
        "1/3 clean processor(s) wrongly flagged under extracted facts.",
      ],
      HELDOUT
    );
    for (const miss of misses) expect(miss).not.toMatch(CODE);
  });
});

describe("groupMetrics", () => {
  it("places every stored metric in a defined group, never Other", () => {
    const groups = groupMetrics(HELDOUT).map((g) => g.group);
    expect(groups).not.toContain("Other");
    expect(groups).toEqual(
      expect.arrayContaining([
        "Risk-band accuracy",
        "Tonnage error",
        "Pattern detection (rule checks)",
        "Pattern detection (agents)",
        "Finding precision",
      ])
    );
  });

  it("drops an unknown row entirely rather than grouping it", () => {
    const metrics = groupMetrics([...HELDOUT, row("agent_run_to_run_agreement", 8, 10)]).flatMap(
      (g) => g.metrics.map((m) => m.metric)
    );
    expect(metrics).not.toContain("agent_run_to_run_agreement");
  });
});

describe("patternCoverage", () => {
  it("counts issue types and planted instances separately", () => {
    const coverage = patternCoverage(HELDOUT)!;

    // 7 rule-check types + the agent-only pair as one; Ghost site and
    // Energy implausibility missed.
    expect(coverage.typesDetected).toBe(6);
    expect(coverage.typesTotal).toBe(8);
    // Capacity inflation is planted on 2 processors, every other rule
    // pattern on 1 (8 rule instances), plus 3 agent-only shipments.
    expect(coverage.instancesDetected).toBe(9);
    expect(coverage.instancesTotal).toBe(11);
    expect(coverage.missed).toEqual(["Ghost Site", "Energy Implausibility"]);
  });

  it("counts the agent-only pair as a missed type when its recall is short", () => {
    const coverage = patternCoverage([
      row("issue_recall_F1_extracted", 2, 2),
      row("agent_citation_recall_extracted", 2, 3),
    ])!;
    expect(coverage.typesDetected).toBe(1);
    expect(coverage.typesTotal).toBe(2);
    expect(coverage.instancesDetected).toBe(4);
    expect(coverage.instancesTotal).toBe(5);
    expect(coverage.missed).toEqual(["Agent-Only Patterns"]);
  });

  it("returns null when the dataset carries no issue-recall rows", () => {
    expect(patternCoverage([row("key_field_read_accuracy", 5430, 5431)])).toBeNull();
  });
});

describe("summaryFigures", () => {
  it("builds the four headline figures from stored rows", () => {
    const figures = summaryFigures(HELDOUT);
    const byKey = Object.fromEntries(figures.map((f) => [f.key, f]));

    expect(figures.map((f) => f.key)).toEqual([
      "risk_band_accuracy",
      "unverifiable_t_pct_error",
      "key_field_read_accuracy",
      "patterns_detected",
    ]);
    expect(byKey.risk_band_accuracy.display).toBe("70% → 90%");
    expect(byKey.risk_band_accuracy.sub).toContain("80% on Extracted Facts");
    expect(byKey.risk_band_accuracy.sub).toContain("Rule Checks → Agent Validation (GROUND-TRUTH FACTS)");
    expect(byKey.unverifiable_t_pct_error.display).toBe("1.95% → 0%");
    expect(byKey.unverifiable_t_pct_error.sub).toBe(
      "Share of True Verifiable Tonnes (GROUND-TRUTH FACTS)"
    );  // identical on both bases here, so no suffix
    expect(byKey.key_field_read_accuracy.display).toBe("99.98%");
    expect(byKey.key_field_read_accuracy.sub).toBe("5,430/5,431 Key Fields");
    expect(byKey.patterns_detected.display).toBe("6/8 (9/11 Instances)");
    expect(byKey.patterns_detected.sub).toBe(
      "Issue Types, With Planted Instances in Brackets · Missed: Ghost Site, Energy Implausibility"
    );
  });

  it("falls back to extracted facts and names that basis when truth rows are absent", () => {
    const rows = HELDOUT.filter((r) => !r.metric.endsWith("_truth"));
    const figures = summaryFigures(rows);
    const band = figures.find((f) => f.key === "risk_band_accuracy")!;

    expect(band.display).toBe("70% → 80%");
    expect(band.sub).toContain("(EXTRACTED FACTS)");
  });

  it("omits a figure whose rows are missing rather than guessing it", () => {
    const keys = summaryFigures([row("key_field_read_accuracy", 5430, 5431)]).map((f) => f.key);
    expect(keys).toEqual(["key_field_read_accuracy"]);
  });
});

describe("annotateMisses", () => {
  it("strips the code and appends surfaced-as-review-flag status", () => {
    const misses = ["F5 ghost site: detected 0/1 planted instance(s) under extracted facts."];
    const rows = [row("issue_surfaced_as_review_flag_F5", 1, 1)];

    expect(annotateMisses(misses, rows)[0]).toBe(
      "Ghost Site: detected 0/1 planted instance(s) under extracted facts. Surfaced as a review flag."
    );
  });

  it("reports a partial surfaced count when not every miss was flagged", () => {
    const misses = ["F7 energy implausibility: detected 0/2 planted instance(s) under extracted facts."];
    const rows = [row("issue_surfaced_as_review_flag_F7", 1, 2)];

    const annotated = annotateMisses(misses, rows)[0];
    expect(annotated).toContain("Energy Implausibility: detected 0/2");
    expect(annotated).toContain("Surfaced as a review flag in 1/2 miss(es).");
  });

  it("strips codes from every miss family, with or without a review-flag row", () => {
    expect(
      annotateMisses(
        [
          "F3 quantity inflation: detected 0/1 planted instance(s) under extracted facts.",
          "F8/F9 (agent-only, no deterministic check): recalled 2/3 true shipment citation(s) under extracted facts.",
        ],
        []
      )
    ).toEqual([
      "Quantity Inflation: detected 0/1 planted instance(s) under extracted facts.",
      "Agent-Only Patterns: recalled 2/3 true shipment citation(s) under extracted facts.",
    ]);
  });

  it("drops the risk-band summary lines, which belong to their own metric card", () => {
    expect(
      annotateMisses(
        [
          "Risk band (checks only, truth facts): 7/10 processor(s) matched the ground-truth band.",
          "Risk band (checks + agents, extracted facts): 8/10 processor(s) matched the ground-truth band.",
          "1/3 clean processor(s) wrongly flagged under extracted facts.",
        ],
        []
      )
    ).toEqual(["1/3 clean processor(s) wrongly flagged under extracted facts."]);
  });

  it("notes that a false flag cost no tonnage, when the stored row says so", () => {
    const misses = ["1/3 clean processor(s) wrongly flagged under extracted facts."];

    expect(annotateMisses(misses, HELDOUT)[0]).toBe(
      "1/3 clean processor(s) wrongly flagged under extracted facts. The flag did not change any " +
        "tonnage — verified tonnes at this stage match ground truth exactly."
    );
  });

  it("adds the diagnosed cause for the dataset it was diagnosed against", () => {
    const misses = ["1/3 clean processor(s) wrongly flagged under extracted facts."];
    const line = annotateMisses(misses, HELDOUT, "heldout-seed7")[0];

    expect(line).toContain("weighbridge ticket");
    expect(line).toContain("one of three identical re-runs");
    expect(line).toContain("rather than a misread document");
  });

  it("never attaches that cause to a dataset it was not diagnosed against", () => {
    const misses = ["1/3 clean processor(s) wrongly flagged under extracted facts."];

    expect(annotateMisses(misses, HELDOUT, "dev-seed42")[0]).not.toContain("weighbridge ticket");
    expect(annotateMisses(misses, HELDOUT, "heldout-seed9")[0]).not.toContain("weighbridge ticket");
  });

  it("omits that note when the stage's tonnage error is not zero", () => {
    const misses = ["1/3 clean processor(s) wrongly flagged under extracted facts."];
    const rows = [row("unverifiable_t_pct_error_full_extracted", 7096, 1_000_000)];

    expect(annotateMisses(misses, rows)).toEqual(misses);
  });

  it("leaves a line it recognises no part of untouched", () => {
    const misses = ["something entirely unexpected from the API."];
    expect(annotateMisses(misses, [])).toEqual(misses);
  });
});


describe("extractedGapNote", () => {
  it("explains the gap as agent variation, never as a reading error", () => {
    const note = extractedGapNote(HELDOUT)!;

    expect(note).toContain("run-to-run variation in the agents' own output, not a reading error");
    expect(note).toContain("9/10");
    expect(note).not.toMatch(/misread|extraction error|field/i);
  });

  it("says nothing when extracted matches ground-truth facts", () => {
    const rows = [
      row("risk_band_accuracy_full_truth", 10, 10),
      row("risk_band_accuracy_full_extracted", 10, 10),
    ];
    expect(extractedGapNote(rows)).toBeNull();
  });
});
