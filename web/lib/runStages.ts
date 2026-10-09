/** Real pipeline stage names from the live-run API (RunStatusOut.status),
 * shared by RunProgress's stage list and ProcessorTabs' docked reasoning
 * panel — a single source of truth so neither ever shows a label the
 * other doesn't recognize. Never fabricated: these are exactly the
 * stage identifiers app/events/run_processor.py reports. */
export const STAGE_ORDER = ["reading_documents", "checking", "reasoning", "drafting_memo"] as const;

export const STAGE_LABEL: Record<string, string> = {
  reading_documents: "Reading documents",
  checking: "Checks",
  reasoning: "Agents reviewing",
  drafting_memo: "Drafting memo",
};
