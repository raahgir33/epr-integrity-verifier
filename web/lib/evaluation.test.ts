import { describe, expect, it } from "vitest";
import { annotateMisses, describeMetric, groupMetrics } from "./evaluation";
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

describe("describeMetric", () => {
  it("labels finding_set_agreement (replaces agent_run_to_run_agreement)", () => {
    const described = describeMetric(row("finding_set_agreement", 8, 10));
    expect(described.group).toBe("Stability, cost and latency");
    expect(described.label).toContain("finding-set agreement");
  });

  it("labels risk_band_stability and unverifiable_t_stability", () => {
    expect(describeMetric(row("risk_band_stability", 9, 10)).label).toContain("Risk-band stability");
    expect(describeMetric(row("unverifiable_t_stability", 10, 10)).label).toContain(
      "Unverifiable-tonnes stability"
    );
  });

  it("labels issue_surfaced_as_review_flag_<code> under its own group", () => {
    const described = describeMetric(row("issue_surfaced_as_review_flag_F5", 1, 1));
    expect(described.group).toBe("Missed-pattern visibility");
    expect(described.label).toContain("F5 ghost site");
  });
});

describe("groupMetrics", () => {
  it("places the new stability/visibility metrics in defined groups, not Other", () => {
    const rows = [
      row("finding_set_agreement", 8, 10),
      row("risk_band_stability", 9, 10),
      row("unverifiable_t_stability", 10, 10),
      row("issue_surfaced_as_review_flag_F7", 0, 1),
    ];
    const groups = groupMetrics(rows).map((g) => g.group);
    expect(groups).not.toContain("Other");
    expect(groups).toEqual(
      expect.arrayContaining(["Stability, cost and latency", "Missed-pattern visibility"])
    );
  });
});

describe("annotateMisses", () => {
  it("appends surfaced-as-review-flag status to a missed F5/F7 line", () => {
    const misses = ["F5 ghost site: detected 0/1 planted instance(s) under extracted facts."];
    const rows = [row("issue_surfaced_as_review_flag_F5", 1, 1)];

    expect(annotateMisses(misses, rows)[0]).toBe(
      "F5 ghost site: detected 0/1 planted instance(s) under extracted facts. Surfaced as a review flag."
    );
  });

  it("reports a partial surfaced count when not every miss was flagged", () => {
    const misses = ["F7 energy implausibility: detected 0/2 planted instance(s) under extracted facts."];
    const rows = [row("issue_surfaced_as_review_flag_F7", 1, 2)];

    expect(annotateMisses(misses, rows)[0]).toContain("Surfaced as a review flag in 1/2 miss(es).");
  });

  it("leaves non-F5/F7 misses and misses with no review-flag row untouched", () => {
    const misses = [
      "F3 quantity inflation: detected 0/1 planted instance(s) under extracted facts.",
      "F5 ghost site: detected 0/1 planted instance(s) under extracted facts.",
    ];

    expect(annotateMisses(misses, [])).toEqual(misses);
  });
});
