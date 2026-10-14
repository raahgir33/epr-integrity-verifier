import type { DemoBatchOut, RunStatusOut } from "@/lib/api";
import { formatMonth, formatSignedTonnes } from "@/lib/format";
import { STAGE_ORDER, STAGE_SHORT_LABEL } from "@/lib/runStages";

/** Derives the live-run task rows from a run (T16b). Pure: data in, rows
 * out, no React and no I/O, so every branch below is unit-testable
 * against a hand-built RunStatusOut — see runRows.test.ts.
 *
 * GET /runs/{run_id} reports exactly four stage keys
 * (app/events/run_processor.py): reading_documents, checking, reasoning,
 * drafting_memo. The panel shows six rows. The extra two are **derived
 * from observable signals**, never from a timer or invented progress:
 *
 * - **Alert decision.** The alert row is written at the end of the
 *   reasoning stage, before finish_stage("reasoning"), so it has no
 *   in-flight window of its own. This row therefore never reports
 *   "in_progress": it goes straight from waiting to done the moment
 *   reasoning completes, carrying the real band change.
 *
 * - **Refreshing results.** cache.invalidate + cache.preload run after
 *   finish_stage("drafting_memo") and before finish("done"), so there is
 *   a genuinely observable window where stage_timestamps.drafting_memo
 *   exists while status is still "drafting_memo". This row spins only
 *   during that window.
 *
 * Both derived rows follow the real stage they depend on when a run
 * fails, rather than inventing a state of their own. */

export type RunRowState = "waiting" | "in_progress" | "done" | "failed";

export type RunRowId =
  | "reading_documents"
  | "checking"
  | "reasoning"
  | "alert_decision"
  | "drafting_memo"
  | "refreshing_results";

export type RunRow = {
  id: RunRowId;
  /** 1-based, shown in the waiting state's outline circle. */
  index: number;
  title: string;
  /** Short muted text to the right of the title; null renders nothing. */
  detail: string | null;
  state: RunRowState;
  tag: "Completed" | "Failed" | null;
  /** True for the two rows with no backing stage key of their own. */
  derived: boolean;
};

const ROW_TITLE: Record<RunRowId, string> = {
  reading_documents: STAGE_SHORT_LABEL.reading_documents,
  checking: STAGE_SHORT_LABEL.checking,
  reasoning: STAGE_SHORT_LABEL.reasoning,
  alert_decision: "Alert decision",
  drafting_memo: STAGE_SHORT_LABEL.drafting_memo,
  refreshing_results: "Refreshing results",
};

/** A failed run reports status "failed", which loses which stage was in
 * flight — so recover it from the timestamps: the first stage with no
 * entry is where it died. Returns null when every stage finished, i.e.
 * the run died later, in the cache re-warm. */
export function failedStage(run: RunStatusOut): string | null {
  if (run.status !== "failed") return null;
  return STAGE_ORDER.find((stage) => !run.stage_timestamps[stage]) ?? null;
}

function realStageState(stage: string, run: RunStatusOut): RunRowState {
  // Checked before the failure branch: a stage that recorded a timestamp
  // genuinely completed, even on a run that failed in a later stage.
  if (run.stage_timestamps[stage]) return "done";
  if (run.status === "failed") return failedStage(run) === stage ? "failed" : "waiting";
  if (run.status === stage) return "in_progress";
  return "waiting";
}

function alertDecisionState(run: RunStatusOut): RunRowState {
  if (run.stage_timestamps.reasoning) return "done";
  if (run.status === "failed") return failedStage(run) === "reasoning" ? "failed" : "waiting";
  return "waiting";
}

function refreshingState(run: RunStatusOut): RunRowState {
  if (run.status === "done") return "done";
  if (run.status === "failed") {
    // Only a failure *after* drafting_memo finished happened in the
    // re-warm; anything earlier never reached this row.
    return run.stage_timestamps.drafting_memo ? "failed" : "waiting";
  }
  if (run.stage_timestamps.drafting_memo && run.status === "drafting_memo") return "in_progress";
  return "waiting";
}

function seconds(value: number): string {
  return `${Math.round(value)} s`;
}

function stageDuration(stage: string, run: RunStatusOut): string | null {
  const timing = run.stage_timestamps[stage];
  return timing ? seconds(timing.duration_s) : null;
}

/** The re-warm has no stage_timestamps entry of its own — it is the gap
 * between drafting_memo finishing and the run going terminal, which is
 * exactly `updated_at - stage_timestamps.drafting_memo.at`. */
function refreshingDuration(run: RunStatusOut): string | null {
  const memo = run.stage_timestamps.drafting_memo;
  if (!memo || run.status !== "done") return null;
  const elapsedMs = new Date(run.updated_at).getTime() - new Date(memo.at).getTime();
  if (!Number.isFinite(elapsedMs) || elapsedMs < 0) return null;
  return seconds(elapsedMs / 1000);
}

function readingDetail(run: RunStatusOut, batch: DemoBatchOut | null): string | null {
  const done = stageDuration("reading_documents", run);
  if (done) return done;
  // Before it finishes there is no duration to show, so the row carries
  // the batch being verified instead — real DemoBatchOut fields, not a
  // document count, which no endpoint in this app reports.
  if (!batch) return null;
  return `${batch.processor_id} · ${formatSignedTonnes(batch.quantity_t)} · ${formatMonth(batch.period_month)}`;
}

function reasoningDetail(run: RunStatusOut): string | null {
  const steps = run.steps.length;
  const tools = run.steps.filter((step) => step.step_type === "critic_tool").length;
  const duration = stageDuration("reasoning", run);
  if (duration) return steps > 0 ? `${steps} steps · ${duration}` : duration;
  if (steps === 0) return null;
  const stepText = `${steps} step${steps === 1 ? "" : "s"}`;
  return tools > 0 ? `${stepText} · ${tools} tool call${tools === 1 ? "" : "s"}` : stepText;
}

function alertDetail(run: RunStatusOut): string | null {
  if (!run.stage_timestamps.reasoning) return null;
  if (!run.alert) return "No change";
  const { risk_band_before: before, risk_band_after: after } = run.alert;
  return before && after ? `${before} → ${after}` : "Alert raised";
}

function tagFor(state: RunRowState): RunRow["tag"] {
  if (state === "done") return "Completed";
  if (state === "failed") return "Failed";
  return null;
}

export function buildRunRows(run: RunStatusOut, batch: DemoBatchOut | null): RunRow[] {
  const spec: { id: RunRowId; state: RunRowState; detail: string | null; derived: boolean }[] = [
    {
      id: "reading_documents",
      state: realStageState("reading_documents", run),
      detail: readingDetail(run, batch),
      derived: false,
    },
    {
      id: "checking",
      state: realStageState("checking", run),
      detail: stageDuration("checking", run),
      derived: false,
    },
    {
      id: "reasoning",
      state: realStageState("reasoning", run),
      detail: reasoningDetail(run),
      derived: false,
    },
    {
      id: "alert_decision",
      state: alertDecisionState(run),
      detail: alertDetail(run),
      derived: true,
    },
    {
      id: "drafting_memo",
      state: realStageState("drafting_memo", run),
      detail: stageDuration("drafting_memo", run),
      derived: false,
    },
    {
      id: "refreshing_results",
      state: refreshingState(run),
      detail: refreshingDuration(run),
      derived: true,
    },
  ];

  return spec.map((row, i) => ({
    id: row.id,
    index: i + 1,
    title: ROW_TITLE[row.id],
    detail: row.detail,
    state: row.state,
    tag: tagFor(row.state),
    derived: row.derived,
  }));
}
