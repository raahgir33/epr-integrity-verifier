import type { FindingOut } from "@/lib/api";

/** Amendment 1 (T12 plan): never render F1-F8/H1-H4 issue codes anywhere in
 * the UI. Every label below is plain language derived from the API's own
 * classification/origin/verdict fields; finding_type/explanation are the
 * agents' own free text and are rendered verbatim by the caller, never a
 * ground-truth field. */

export function isDisplayedFinding(finding: FindingOut): boolean {
  // withdrawn = trail-only, no scoring effect (docs/DATA_SPEC.md §4a) — not
  // shown as a standalone finding.
  return finding.classification !== "withdrawn";
}

export function agreementLabel(finding: FindingOut): string {
  return finding.classification === "review_flag"
    ? "Flagged for review, agents disagreed"
    : "Both agents agreed";
}

export function classificationLabel(finding: FindingOut): string {
  switch (finding.classification) {
    case "deductible":
      return "Confirmed, tonnes deducted from the verifiable total";
    case "systemic":
      return "Too broad to deduct automatically, flagged for review";
    case "no_own_evidence":
      return "No shipment-level evidence for every cited shipment, flagged for review, not deducted";
    case "concurs_with_check":
      return "Independently confirmed, already caught by a deterministic check";
    case "review_flag":
      return "Disputed between agents, kept for review, not deducted";
    default:
      return finding.classification;
  }
}

export function originLabel(finding: FindingOut): string {
  return finding.proposed_by === "hypothesis" ? "Raised by the Hypothesis agent" : "Raised by the Critic agent";
}
