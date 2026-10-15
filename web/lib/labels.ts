/** Plain display names for the two identifier vocabularies the UI surfaces
 * (T16c, findings F8 and F12).
 *
 * Both maps are display-only: they never alter an ID, a status, a
 * threshold or a computed figure, and the raw identifier stays visible
 * beside the name wherever it was already shown (evidence chips, the
 * check cards' own code). Unknown values fall back to a humanised form of
 * the identifier rather than rendering blank, so a new document type or
 * check added on the API side still reads sensibly before this file
 * catches up.
 */

/** Source: the names already written on the Method page
 * (components/method/RuleBasedChecksAccordion.tsx's CHECKS list), lifted
 * here so a check reads the same wherever it is cited. C3 is split into
 * its two API-level ids: C3a is the implied-average-speed test, C3b the
 * e-way bill validity window — both described under "Transport
 * plausibility" in that same list. */
const CHECK_NAMES: Record<string, string> = {
  C1: "Certified tonnes within consented capacity",
  C2a: "Certified tonnes within verified inbound waste",
  C2b: "Recycled output within processed tonnes and yield",
  C3a: "Transport speed plausibility",
  C3b: "E-way bill validity window",
  C4: "Cross-document consistency",
  C5: "Duplicate document use",
  C6: "Consent validity and permitted category",
  C7: "Electricity plausibility",
  C8: "Site plausibility",
};

const DOC_TYPE_NAMES: Record<string, string> = {
  cto: "Consent to Operate",
  electricity_bill: "Electricity bill",
  epr_registration: "EPR registration",
  eway_bill: "E-way bill",
  inbound_invoice: "Inbound invoice",
  outbound_invoice: "Outbound invoice",
  weighbridge_slip: "Weighbridge slip",
};

/** snake_case / SCREAMING_CASE -> "Sentence case words". */
function humanise(raw: string): string {
  const words = raw.replace(/[_-]+/g, " ").trim().toLowerCase();
  if (!words) return raw;
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function checkName(checkId: string): string {
  return CHECK_NAMES[checkId] ?? humanise(checkId);
}

/** The check as prose: "C6 (consent validity and permitted category)" —
 * used where a bare code would otherwise land in a sentence. */
export function checkNameWithCode(checkId: string): string {
  const name = CHECK_NAMES[checkId];
  return name ? `${checkId} (${name.charAt(0).toLowerCase()}${name.slice(1)})` : checkId;
}

export function docTypeName(docType: string): string {
  return DOC_TYPE_NAMES[docType] ?? humanise(docType);
}
