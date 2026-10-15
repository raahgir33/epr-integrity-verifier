import type { FindingOut, StageAssessment } from "@/lib/api";
import { formatTonnes } from "@/lib/format";

/** Sub-lines for the Overview tab's two finding tiles (T17).
 *
 * The counts themselves, and the classification buckets behind them, are
 * unchanged — "Confirmed findings" still counts `concurs_with_check`
 * alongside `deductible`. The problem was that a count alone is
 * unreadable: PWP-10 and PWP-07 show "Confirmed findings: 1" with 0.00 t
 * unverifiable, because their one confirmed finding only agrees with a
 * rule check and deducts nothing of its own. These sub-lines say which
 * kind the count is made of, so the number stops looking like a
 * contradiction.
 *
 * Built from the `classification` field only, plus — for the deducted
 * tonnage — the gap between the two stored assessment stages, which is
 * the agent stage's whole contribution by definition.
 *
 * Deliberately conservative about attributing that tonnage. It is quoted
 * only when at least one `deductible` finding exists, and never attached
 * to the review tile: PWP-05 currently carries two `no_own_evidence`
 * findings alongside a +7.04 t gap, so "flagged, not deducted" would be
 * a false claim about live data. The review line therefore states the
 * count and nothing more. */
const CONFIRMED = new Set(["deductible", "concurs_with_check"]);
const REVIEW = new Set(["systemic", "no_own_evidence", "review_flag"]);

/** Below this the gap is rounding noise, not a deduction worth naming. */
const TONNES_EPSILON = 0.005;

function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}

export function findingsBreakdown(
  findings: FindingOut[],
  checksOnly: StageAssessment,
  full: StageAssessment | null,
): { confirmedBreakdown?: string; reviewBreakdown?: string } {
  const deductible = findings.filter((f) => f.classification === "deductible").length;
  const concurs = findings.filter((f) => f.classification === "concurs_with_check").length;
  const review = findings.filter((f) => REVIEW.has(f.classification)).length;

  // The agent stage's own effect on the verifiable total.
  const deducted = full ? full.unverifiable_t - checksOnly.unverifiable_t : 0;

  const confirmedParts: string[] = [];
  if (deductible > 0) {
    confirmedParts.push(
      deducted > TONNES_EPSILON
        ? `${deductible} ${plural(deductible, "deducts", "deduct")} ${formatTonnes(deducted)}`
        : `${deductible} confirmed`,
    );
  }
  if (concurs > 0) {
    const agrees = `${concurs} ${plural(concurs, "agrees", "agree")} with a rule check`;
    // Only safe to call out the absence of a deduction when nothing in
    // this tile deducts.
    confirmedParts.push(deductible === 0 ? `${agrees} · no extra deduction` : agrees);
  }

  return {
    confirmedBreakdown: confirmedParts.length > 0 ? confirmedParts.join(" · ") : undefined,
    reviewBreakdown: review > 0 ? `${review} flagged for review` : undefined,
  };
}

export const CONFIRMED_CLASSIFICATIONS = CONFIRMED;
export const REVIEW_CLASSIFICATIONS = REVIEW;
