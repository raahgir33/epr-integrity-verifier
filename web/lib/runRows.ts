import type { DemoBatchOut, ReasoningStepOut, RunStatusOut } from "@/lib/api";
import { formatIstTime, formatMonth, formatSignedTonnes } from "@/lib/format";
import { stepActionLine } from "@/lib/reasoning";
import { STAGE_ORDER, STAGE_SHORT_LABEL } from "@/lib/runStages";
import { titleCase } from "@/lib/titleCase";

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

/** One line in an expanded row's body: a label on the left, an optional
 * value on the right. `mono` sets the value in the code face, matching
 * how tool names and measured figures are set elsewhere in the app. */
export type RunRowLine = {
  label: string;
  value: string | null;
  mono?: boolean;
};

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
  /** Body content, shown when the row is expanded. */
  lines: RunRowLine[];
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


// --- expanded body ------------------------------------------------------
//
// Every line below is read off the run itself. There is no document count
// and no check count anywhere in GET /runs/{run_id}, so neither appears
// here: what a stage row can honestly show is when it finished, how long
// it took, and — when it failed — the error the backend reported.

function statusLine(state: RunRowState): RunRowLine {
  const label =
    state === "waiting"
      ? "Not started yet"
      : state === "in_progress"
        ? "Running now"
        : state === "failed"
          ? "Failed"
          : "Completed";
  return { label, value: null };
}

/** Timing lines shared by the three plain stage rows. */
function stageLines(stage: string, run: RunStatusOut, state: RunRowState): RunRowLine[] {
  const timing = run.stage_timestamps[stage];
  if (timing) {
    const finished = formatIstTime(timing.at);
    return [
      ...(finished ? [{ label: "Finished at", value: finished, mono: true }] : []),
      { label: "Took", value: seconds(timing.duration_s), mono: true },
    ];
  }
  if (state === "failed") {
    return [
      statusLine(state),
      ...(run.error_message ? [{ label: "Error", value: run.error_message, mono: true }] : []),
    ];
  }
  return [statusLine(state)];
}

/** The reasoning row's body is the live trail itself — the same steps
 * ReasoningTimeline renders on the processor page, read from run.steps
 * rather than from any new field. Oldest first, so an arriving step is
 * appended at the bottom instead of displacing what is already on
 * screen. The value is each step's measured latency where the backend
 * reported one; nothing is shown where it did not. */
function reasoningLines(run: RunStatusOut, state: RunRowState): RunRowLine[] {
  if (run.steps.length === 0) {
    return state === "failed"
      ? [
          statusLine(state),
          ...(run.error_message ? [{ label: "Error", value: run.error_message, mono: true }] : []),
        ]
      : [statusLine(state)];
  }
  const lines: RunRowLine[] = run.steps.map((step: ReasoningStepOut) => ({
    label: titleCase(stepActionLine(step)),
    value: step.latency_ms === null ? null : `${Math.round(step.latency_ms)} ms`,
    mono: true,
  }));
  if (state === "failed" && run.error_message) {
    lines.push({ label: "Error", value: run.error_message, mono: true });
  }
  return lines;
}

/** The row's own detail already carries the band change, so the body adds
 * what a short detail cannot: the alert's full sentence and the finding
 * behind it. Repeating "Medium → High" in both places would spend the
 * body's only lines on something already on screen. */
function alertLines(run: RunStatusOut, state: RunRowState): RunRowLine[] {
  if (state !== "done") return [statusLine(state)];
  if (!run.alert) return [{ label: "Risk band unchanged, no new finding.", value: null }];
  const finding = run.alert.new_finding_summary;
  return [
    { label: run.alert.message, value: null },
    ...(finding ? [{ label: `New finding: ${finding}`, value: null }] : []),
  ];
}

/** The re-warm has no stage entry, so its only honest timing is the gap
 * already derived for the row's own detail. */
function refreshingLines(run: RunStatusOut, state: RunRowState): RunRowLine[] {
  const took = refreshingDuration(run);
  if (took) return [{ label: "Took", value: took, mono: true }];
  if (state === "failed") {
    return [
      statusLine(state),
      ...(run.error_message ? [{ label: "Error", value: run.error_message, mono: true }] : []),
    ];
  }
  return [statusLine(state)];
}

function linesFor(id: RunRowId, run: RunStatusOut, state: RunRowState): RunRowLine[] {
  switch (id) {
    case "reasoning":
      return reasoningLines(run, state);
    case "alert_decision":
      return alertLines(run, state);
    case "refreshing_results":
      return refreshingLines(run, state);
    default:
      return stageLines(id, run, state);
  }
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
    lines: linesFor(row.id, run, row.state),
  }));
}
