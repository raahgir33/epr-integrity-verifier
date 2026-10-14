/** Real pipeline stage names from the live-run API (RunStatusOut.status),
 * shared by RunProgress's stage list and ProcessorTabs' docked reasoning
 * panel — a single source of truth so neither ever shows a label the
 * other doesn't recognize. Never fabricated: these are exactly the
 * stage identifiers app/events/run_processor.py reports. */
export const STAGE_ORDER = ["reading_documents", "checking", "reasoning", "drafting_memo"] as const;

export const STAGE_LABEL: Record<string, string> = {
  reading_documents: "Extract & Read Documents",
  checking: "Perform Rule-based Checks",
  reasoning: "Review & Grade Findings - HYPTHOSES and CRITIC",
  drafting_memo: "Draft Memo, Verification Statement & Findings",
};

/** Short titles for the landing page's task rows (T16b), which are pill
 * shaped and truncate: STAGE_LABEL's sentences are written for the
 * processor page's wider stage list and would be ellipsed to nothing
 * here. Deliberately a second map beside STAGE_LABEL rather than a
 * replacement for it — the two render in different places at different
 * widths — but kept in this same file so there is still one place to
 * look when a stage name changes. Same keys, same order, same source:
 * these are the stage identifiers app/events/run_processor.py reports. */
export const STAGE_SHORT_LABEL: Record<(typeof STAGE_ORDER)[number], string> = {
  reading_documents: "Reading documents",
  checking: "Running checks",
  reasoning: "Agent reasoning",
  drafting_memo: "Drafting memo",
};
