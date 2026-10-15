import { describe, expect, it } from "vitest";
import type { FindingOut, StageAssessment } from "@/lib/api";
import { findingsBreakdown } from "@/lib/findingsBreakdown";

function finding(classification: string): FindingOut {
  return {
    finding_type: "Example",
    classification,
    effect: "raises_concern",
    cited_shipment_ids: [],
    evidence_ids: [],
    explanation: "",
    origin: "critic",
    proposed_by: "critic",
    verdict: null,
    disputed_by: null,
  } as unknown as FindingOut;
}

function stage(unverifiable_t: number): StageAssessment {
  return {
    certified_t: 100,
    verified_inbound_t: 100 - unverifiable_t,
    capacity_limit_t: 200,
    verifiable_t: 100 - unverifiable_t,
    unverifiable_t,
    risk_band: "Low",
  } as StageAssessment;
}

describe("findingsBreakdown", () => {
  it("says nothing when there are no findings", () => {
    expect(findingsBreakdown([], stage(0), stage(0))).toEqual({
      confirmedBreakdown: undefined,
      reviewBreakdown: undefined,
    });
  });

  // PWP-10 and PWP-07 live: one concurs_with_check finding, no gap
  // between the stages. This is the case the sub-line exists for — a
  // count of 1 beside 0.00 t unverifiable (PWP-10, Low) or beside a band
  // the rule checks alone explain (PWP-07, High).
  it("explains a lone rule-check agreement, the PWP-10 and PWP-07 case", () => {
    const { confirmedBreakdown, reviewBreakdown } = findingsBreakdown(
      [finding("concurs_with_check")],
      stage(0),
      stage(0),
    );
    expect(confirmedBreakdown).toBe("1 agrees with a rule check · no extra deduction");
    expect(reviewBreakdown).toBeUndefined();
  });

  // PWP-03 after a live run on BATCH-PWP-03-001: the planted handwritten
  // remark is deductible, and the agent stage adds 8.45 t.
  it("quotes the deducted tonnage, the PWP-03 post-run case", () => {
    const { confirmedBreakdown } = findingsBreakdown(
      [finding("deductible")],
      stage(0),
      stage(8.45),
    );
    expect(confirmedBreakdown).toBe("1 deducts 8.45 t");
  });

  // PWP-05 live: two no_own_evidence findings alongside a +7.04 t gap
  // between the stages. The review line must not claim "not deducted" —
  // on this processor that would be false.
  it("states the review count without claiming anything about tonnage, the PWP-05 case", () => {
    const { confirmedBreakdown, reviewBreakdown } = findingsBreakdown(
      [finding("no_own_evidence"), finding("no_own_evidence")],
      stage(78.81),
      stage(85.85),
    );
    expect(confirmedBreakdown).toBeUndefined();
    expect(reviewBreakdown).toBe("2 flagged for review");
    expect(reviewBreakdown).not.toContain("not deducted");
  });

  it("drops the no-extra-deduction note when something in the tile does deduct", () => {
    const { confirmedBreakdown } = findingsBreakdown(
      [finding("deductible"), finding("concurs_with_check")],
      stage(0),
      stage(8.45),
    );
    expect(confirmedBreakdown).toBe("1 deducts 8.45 t · 1 agrees with a rule check");
    expect(confirmedBreakdown).not.toContain("no extra deduction");
  });

  it("does not quote a rounding-noise gap as a deduction", () => {
    const { confirmedBreakdown } = findingsBreakdown(
      [finding("deductible")],
      stage(5),
      stage(5.001),
    );
    expect(confirmedBreakdown).toBe("1 confirmed");
  });

  it("omits the tonnage when the agent stage has not run", () => {
    const { confirmedBreakdown } = findingsBreakdown([finding("deductible")], stage(0), null);
    expect(confirmedBreakdown).toBe("1 confirmed");
  });

  it("agrees in the plural", () => {
    expect(
      findingsBreakdown(
        [finding("concurs_with_check"), finding("concurs_with_check")],
        stage(0),
        stage(0),
      ).confirmedBreakdown,
    ).toBe("2 agree with a rule check · no extra deduction");
  });
});
