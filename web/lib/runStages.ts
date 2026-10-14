/** Real pipeline stage names from the live-run API (RunStatusOut.status),
 * used by the landing page's live-run task rows — a single source of
 * truth so nothing ever shows a label the API doesn't report. Never
 * fabricated: these are exactly the
 * stage identifiers app/events/run_processor.py reports.
 *
 * T16b: the long-form STAGE_LABEL map that used to sit here went with
 * the processor page's live-run control — its only two render sites were
 * reached through it. STAGE_SHORT_LABEL below is what the landing
 * page's task rows use. */
export const STAGE_ORDER = ["reading_documents", "checking", "reasoning", "drafting_memo"] as const;


/** Short titles for the landing page's task rows (T16b), which are pill
 * shaped and truncate. Same keys, same order, same source as
 * STAGE_ORDER:
 * these are the stage identifiers app/events/run_processor.py reports. */
export const STAGE_SHORT_LABEL: Record<(typeof STAGE_ORDER)[number], string> = {
  reading_documents: "Reading documents",
  checking: "Running checks",
  reasoning: "Agent reasoning",
  drafting_memo: "Drafting memo",
};
