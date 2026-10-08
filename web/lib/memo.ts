import type { components } from "@/lib/api-types";

export type ClarificationMemo = components["schemas"]["ClarificationMemo"];
export type VerificationStatement = components["schemas"]["VerificationStatement"];

/** doc_type lives on the sibling MemoResponse, not inside the memo union
 * itself, so TypeScript can't narrow ClarificationMemo | VerificationStatement
 * on its own — this is the explicit type guard every memo component uses. */
export function isClarificationMemo(
  docType: string,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars -- used in the `doc is ClarificationMemo` type predicate below, not at runtime
  doc: ClarificationMemo | VerificationStatement,
): doc is ClarificationMemo {
  return docType === "clarification_memo";
}

/** Plain-text rendering for the Copy button — never for a hidden download,
 * the viewer's sandbox blocks those; this is clipboard text only. */
export function renderMemoAsPlainText(
  docType: string,
  doc: ClarificationMemo | VerificationStatement,
  senderLine: string,
): string {
  const lines: string[] = [senderLine, "", doc.subject, "", doc.salutation, ""];

  if (isClarificationMemo(docType, doc)) {
    lines.push(doc.opening_paragraph, "");
    doc.items.forEach((item, i) => {
      lines.push(`${i + 1}. ${item.heading}`);
      lines.push(item.what_we_observed);
      lines.push(`What we request: ${item.what_we_request}`);
      if (item.evidence_ids.length > 0) lines.push(`Evidence: ${item.evidence_ids.join(", ")}`);
      lines.push("");
    });
    lines.push(`We request a response within ${doc.response_deadline_days} days of this letter.`);
    lines.push("");
    lines.push(doc.closing_paragraph);
  } else {
    lines.push(doc.part_a_paragraph, "");
    if (doc.observations.length > 0) {
      doc.observations.forEach((obs, i) => {
        lines.push(`${i + 1}. ${obs.recommendation}`);
        if (obs.evidence_ids.length > 0) lines.push(`Evidence: ${obs.evidence_ids.join(", ")}`);
        lines.push("");
      });
    } else if (doc.no_items_note) {
      lines.push(doc.no_items_note, "");
    }
    lines.push(doc.closing_paragraph);
  }

  return lines.join("\n");
}
