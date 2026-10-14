import { describe, expect, it } from "vitest";
import type { DemoBatchOut, RunStatusOut } from "@/lib/api";
import { buildRunRows, failedStage, type RunRowId, type RunRowState } from "@/lib/runRows";

const BATCH: DemoBatchOut = {
  batch_id: "BATCH-PWP-05-001",
  period_month: "2026-03",
  processor_id: "PWP-05",
  pushes_over_verifiable: true,
  quantity_t: 8.45,
};

const ALERT = {
  alert_id: "ALERT-1",
  created_at: "2026-03-31T10:04:00Z",
  message: "Risk band rose from Medium to High after the new certificate batch.",
  new_finding_summary: null,
  processor_id: "PWP-05",
  risk_band_after: "High",
  risk_band_before: "Medium",
  run_id: "run-1",
};

const START = "2026-03-31T10:00:00Z";

function timing(offsetS: number, durationS: number) {
  return { at: new Date(Date.parse(START) + offsetS * 1000).toISOString(), duration_s: durationS };
}

function step(index: number, type: string) {
  return {
    step_index: index,
    step_type: type,
    tool_name: type === "critic_tool" ? "read_document" : null,
    tool_args: null,
    result: null,
    result_summary: null,
    output: null,
    tokens: null,
    latency_ms: null,
    dedup_hit: false,
  };
}

function run(overrides: Partial<RunStatusOut>): RunStatusOut {
  return {
    meta: { seed: 42, facts_source: "truth" },
    run_id: "run-1",
    batch_id: BATCH.batch_id,
    processor_id: "PWP-05",
    status: "queued",
    created_at: START,
    updated_at: START,
    stage_timestamps: {},
    steps: [],
    error_message: null,
    alert: null,
    ...overrides,
  } as RunStatusOut;
}

/** states keyed by row id, so assertions read as the panel looks. */
function states(r: RunStatusOut): Record<RunRowId, RunRowState> {
  return Object.fromEntries(buildRunRows(r, BATCH).map((row) => [row.id, row.state])) as Record<
    RunRowId,
    RunRowState
  >;
}

function detail(r: RunStatusOut, id: RunRowId): string | null {
  return buildRunRows(r, BATCH).find((row) => row.id === id)?.detail ?? null;
}

describe("buildRunRows — shape", () => {
  it("always returns the six rows in pipeline order, numbered from 1", () => {
    const rows = buildRunRows(run({}), BATCH);
    expect(rows.map((r) => r.id)).toEqual([
      "reading_documents",
      "checking",
      "reasoning",
      "alert_decision",
      "drafting_memo",
      "refreshing_results",
    ]);
    expect(rows.map((r) => r.index)).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it("marks exactly the two rows with no backing stage key as derived", () => {
    const derived = buildRunRows(run({}), BATCH).filter((r) => r.derived);
    expect(derived.map((r) => r.id)).toEqual(["alert_decision", "refreshing_results"]);
  });

  it("tags only terminal rows", () => {
    const rows = buildRunRows(
      run({ status: "checking", stage_timestamps: { reading_documents: timing(10, 10) } }),
      BATCH,
    );
    expect(rows.find((r) => r.id === "reading_documents")?.tag).toBe("Completed");
    expect(rows.find((r) => r.id === "checking")?.tag).toBeNull();
    expect(rows.find((r) => r.id === "drafting_memo")?.tag).toBeNull();
  });
});

describe("buildRunRows — a run that completes", () => {
  const queued = run({ status: "queued" });
  const done = run({
    status: "done",
    updated_at: new Date(Date.parse(START) + 103 * 1000).toISOString(),
    stage_timestamps: {
      reading_documents: timing(12, 12),
      checking: timing(30, 18),
      reasoning: timing(90, 60),
      drafting_memo: timing(100, 10),
    },
    steps: [step(0, "hypothesis"), step(1, "critic_tool"), step(2, "critic_tool")],
    alert: ALERT,
  });

  it("starts every row waiting", () => {
    expect(Object.values(states(queued)).every((s) => s === "waiting")).toBe(true);
  });

  it("ends with every row done", () => {
    expect(Object.values(states(done)).every((s) => s === "done")).toBe(true);
  });

  it("shows the batch while reading, then the measured duration", () => {
    expect(detail(queued, "reading_documents")).toBe("PWP-05 · +8.45 t · Mar 2026");
    expect(detail(done, "reading_documents")).toBe("12 s");
  });

  it("reports the real band change on the derived alert row", () => {
    expect(detail(done, "alert_decision")).toBe("Medium → High");
  });

  it("derives the re-warm duration from updated_at minus the memo timestamp", () => {
    // drafting_memo finished at +100s, run went terminal at +103s.
    expect(detail(done, "refreshing_results")).toBe("3 s");
  });

  it("counts live steps and tool calls while reasoning, then adds the duration", () => {
    const live = run({
      status: "reasoning",
      stage_timestamps: { reading_documents: timing(12, 12), checking: timing(30, 18) },
      steps: [step(0, "hypothesis"), step(1, "critic_tool")],
    });
    expect(detail(live, "reasoning")).toBe("2 steps · 1 tool call");
    expect(detail(done, "reasoning")).toBe("3 steps · 60 s");
  });
});

describe("buildRunRows — the derived rows never invent a state", () => {
  it("never reports the alert row as in progress, at any point in a run", () => {
    const points = [
      run({ status: "queued" }),
      run({ status: "reading_documents" }),
      run({ status: "checking", stage_timestamps: { reading_documents: timing(12, 12) } }),
      run({
        status: "reasoning",
        stage_timestamps: { reading_documents: timing(12, 12), checking: timing(30, 18) },
      }),
      run({
        status: "drafting_memo",
        stage_timestamps: {
          reading_documents: timing(12, 12),
          checking: timing(30, 18),
          reasoning: timing(90, 60),
        },
        alert: ALERT,
      }),
    ];
    for (const r of points) expect(states(r).alert_decision).not.toBe("in_progress");
  });

  it("completes the alert row together with reasoning, not later", () => {
    const s = states(
      run({
        status: "drafting_memo",
        stage_timestamps: {
          reading_documents: timing(12, 12),
          checking: timing(30, 18),
          reasoning: timing(90, 60),
        },
        alert: ALERT,
      }),
    );
    expect(s.reasoning).toBe("done");
    expect(s.alert_decision).toBe("done");
    expect(s.drafting_memo).toBe("in_progress");
  });

  it("spins the re-warm row only in its real window", () => {
    const base = {
      reading_documents: timing(12, 12),
      checking: timing(30, 18),
      reasoning: timing(90, 60),
    };
    // drafting_memo in flight: the re-warm has not started.
    expect(states(run({ status: "drafting_memo", stage_timestamps: base })).refreshing_results).toBe(
      "waiting",
    );
    // drafting_memo finished but status still drafting_memo: re-warm running.
    expect(
      states(
        run({
          status: "drafting_memo",
          stage_timestamps: { ...base, drafting_memo: timing(100, 10) },
        }),
      ).refreshing_results,
    ).toBe("in_progress");
  });
});

describe("buildRunRows — a run with no alert", () => {
  const noAlert = run({
    status: "done",
    updated_at: new Date(Date.parse(START) + 103 * 1000).toISOString(),
    stage_timestamps: {
      reading_documents: timing(12, 12),
      checking: timing(30, 18),
      reasoning: timing(90, 60),
      drafting_memo: timing(100, 10),
    },
    alert: null,
  });

  it("still completes the alert row", () => {
    expect(states(noAlert).alert_decision).toBe("done");
  });

  it("says so rather than leaving the detail blank", () => {
    expect(detail(noAlert, "alert_decision")).toBe("No change");
  });
});

describe("buildRunRows — a skipped stage", () => {
  // A batch with no extra documents still records a reading_documents
  // timestamp: run_processor.py calls finish_stage unconditionally, with
  // only the work inside `if extra_document_ids:`. So the row must read
  // as completed, never as failed or stuck in progress.
  const skipped = run({
    status: "done",
    updated_at: new Date(Date.parse(START) + 103 * 1000).toISOString(),
    stage_timestamps: {
      reading_documents: timing(0.1, 0.1),
      checking: timing(30, 18),
      reasoning: timing(90, 60),
      drafting_memo: timing(100, 10),
    },
    alert: ALERT,
  });

  it("completes the near-zero-duration stage", () => {
    expect(states(skipped).reading_documents).toBe("done");
  });

  it("never reads as failed or in progress", () => {
    const s = states(skipped).reading_documents;
    expect(s).not.toBe("failed");
    expect(s).not.toBe("in_progress");
  });

  it("rounds its duration rather than printing a fraction", () => {
    expect(detail(skipped, "reading_documents")).toBe("0 s");
  });
});

describe("buildRunRows — failure in each stage", () => {
  const cases: { stage: string; before: RunStatusOut["stage_timestamps"] }[] = [
    { stage: "reading_documents", before: {} },
    { stage: "checking", before: { reading_documents: timing(12, 12) } },
    {
      stage: "reasoning",
      before: { reading_documents: timing(12, 12), checking: timing(30, 18) },
    },
    {
      stage: "drafting_memo",
      before: {
        reading_documents: timing(12, 12),
        checking: timing(30, 18),
        reasoning: timing(90, 60),
      },
    },
  ];

  for (const { stage, before } of cases) {
    it(`marks ${stage} failed, earlier rows done and later rows waiting`, () => {
      const r = run({ status: "failed", stage_timestamps: before, error_message: "boom" });
      expect(failedStage(r)).toBe(stage);
      const s = states(r);

      // Exactly one real row failed.
      const failedRows = Object.entries(s).filter(([, v]) => v === "failed");
      expect(failedRows.length).toBeGreaterThanOrEqual(1);
      expect(s[stage as RunRowId]).toBe("failed");

      // Nothing is left spinning on a terminal run.
      expect(Object.values(s)).not.toContain("in_progress");

      // Stages that recorded a timestamp still read as done.
      for (const key of Object.keys(before)) expect(s[key as RunRowId]).toBe("done");
    });
  }

  it("fails the alert row only when reasoning itself failed", () => {
    const inReasoning = run({
      status: "failed",
      stage_timestamps: { reading_documents: timing(12, 12), checking: timing(30, 18) },
    });
    expect(states(inReasoning).alert_decision).toBe("failed");

    const inChecking = run({
      status: "failed",
      stage_timestamps: { reading_documents: timing(12, 12) },
    });
    expect(states(inChecking).alert_decision).toBe("waiting");

    const inMemo = run({
      status: "failed",
      stage_timestamps: {
        reading_documents: timing(12, 12),
        checking: timing(30, 18),
        reasoning: timing(90, 60),
      },
    });
    // Reasoning completed, so the alert decision genuinely happened.
    expect(states(inMemo).alert_decision).toBe("done");
  });

  it("leaves the re-warm row waiting when the run died before drafting_memo finished", () => {
    const r = run({
      status: "failed",
      stage_timestamps: {
        reading_documents: timing(12, 12),
        checking: timing(30, 18),
        reasoning: timing(90, 60),
      },
    });
    expect(states(r).refreshing_results).toBe("waiting");
  });
});

describe("buildRunRows — failure during the cache re-warm", () => {
  const r = run({
    status: "failed",
    stage_timestamps: {
      reading_documents: timing(12, 12),
      checking: timing(30, 18),
      reasoning: timing(90, 60),
      drafting_memo: timing(100, 10),
    },
    alert: ALERT,
    error_message: "cache preload failed",
  });

  it("has no failed stage key, because every stage finished", () => {
    expect(failedStage(r)).toBeNull();
  });

  it("fails the re-warm row and leaves every other row done", () => {
    const s = states(r);
    expect(s.refreshing_results).toBe("failed");
    expect(s.reading_documents).toBe("done");
    expect(s.checking).toBe("done");
    expect(s.reasoning).toBe("done");
    expect(s.alert_decision).toBe("done");
    expect(s.drafting_memo).toBe("done");
  });

  it("shows no re-warm duration, since the run never reached done", () => {
    expect(detail(r, "refreshing_results")).toBeNull();
  });
});

describe("buildRunRows — without a batch", () => {
  it("omits the batch detail rather than rendering a partial string", () => {
    expect(buildRunRows(run({ status: "reading_documents" }), null)[0].detail).toBeNull();
  });
});

describe("buildRunRows — expanded body lines", () => {
  const base = {
    reading_documents: timing(12, 12),
    checking: timing(30, 18),
    reasoning: timing(90, 60),
  };

  it("shows when a finished stage finished, and how long it took", () => {
    const r = run({ status: "checking", stage_timestamps: { reading_documents: timing(12, 12) } });
    const lines = buildRunRows(r, BATCH)[0].lines;
    expect(lines.map((l) => l.label)).toEqual(["Finished at", "Took"]);
    expect(lines[1].value).toBe("12 s");
    // IST, pinned rather than left to the test runner's zone: the stage
    // finished at 10:00:12 UTC, which is 15:30:12 in Asia/Kolkata.
    expect(lines[0].value).toBe("15:30:12 IST");
  });

  it("says a stage has not started rather than showing an empty body", () => {
    expect(buildRunRows(run({ status: "queued" }), BATCH)[1].lines).toEqual([
      { label: "Not started yet", value: null },
    ]);
  });

  it("marks the running stage as running", () => {
    const r = run({ status: "checking", stage_timestamps: { reading_documents: timing(12, 12) } });
    expect(buildRunRows(r, BATCH)[1].lines).toEqual([{ label: "Running now", value: null }]);
  });

  it("carries the backend's error onto the stage that failed", () => {
    const r = run({
      status: "failed",
      stage_timestamps: { reading_documents: timing(12, 12) },
      error_message: "checking failed: boom",
    });
    const lines = buildRunRows(r, BATCH)[1].lines;
    expect(lines[0]).toEqual({ label: "Failed", value: null });
    expect(lines[1]).toEqual({ label: "Error", value: "checking failed: boom", mono: true });
  });

  it("fills the reasoning body with the real steps, oldest first, with their latencies", () => {
    const r = run({
      status: "reasoning",
      stage_timestamps: { reading_documents: timing(12, 12), checking: timing(30, 18) },
      steps: [
        { ...step(0, "hypothesis"), latency_ms: 1840 },
        { ...step(1, "critic_tool"), latency_ms: 920 },
      ],
    });
    const lines = buildRunRows(r, BATCH)[2].lines;
    expect(lines).toHaveLength(2);
    expect(lines[1].label).toContain("read_document");
    expect(lines.map((l) => l.value)).toEqual(["1840 ms", "920 ms"]);
  });

  it("omits a latency the backend did not report rather than inventing one", () => {
    const r = run({
      status: "reasoning",
      stage_timestamps: { reading_documents: timing(12, 12), checking: timing(30, 18) },
      steps: [step(0, "hypothesis")],
    });
    expect(buildRunRows(r, BATCH)[2].lines[0].value).toBeNull();
  });

  it("spends the alert body on the message and finding, not on the band change already in the detail", () => {
    const r = run({
      status: "drafting_memo",
      stage_timestamps: base,
      alert: { ...ALERT, new_finding_summary: "Certified tonnes exceed verified inbound waste." },
    });
    const row = buildRunRows(r, BATCH)[3];
    expect(row.detail).toBe("Medium → High");
    expect(row.lines[0].label).toBe(ALERT.message);
    expect(row.lines[1].label).toContain("Certified tonnes exceed");
    // The detail already says it; the body must not repeat it.
    expect(row.lines.some((l) => l.value === "Medium → High")).toBe(false);
  });

  it("says so plainly when no alert fired", () => {
    const r = run({ status: "drafting_memo", stage_timestamps: base, alert: null });
    expect(buildRunRows(r, BATCH)[3].lines[0].label).toBe("Risk band unchanged, no new finding.");
  });

  it("gives the re-warm row its derived duration once the run is done", () => {
    const r = run({
      status: "done",
      updated_at: new Date(Date.parse(START) + 103 * 1000).toISOString(),
      stage_timestamps: { ...base, drafting_memo: timing(100, 10) },
      alert: ALERT,
    });
    expect(buildRunRows(r, BATCH)[5].lines).toEqual([{ label: "Took", value: "3 s", mono: true }]);
  });

  it("never leaves a row with an empty body", () => {
    const points = [
      run({ status: "queued" }),
      run({ status: "reasoning", stage_timestamps: { reading_documents: timing(12, 12) } }),
      run({ status: "failed", stage_timestamps: base, error_message: "boom" }),
      run({
        status: "done",
        updated_at: new Date(Date.parse(START) + 103 * 1000).toISOString(),
        stage_timestamps: { ...base, drafting_memo: timing(100, 10) },
        alert: ALERT,
      }),
    ];
    for (const r of points) {
      for (const row of buildRunRows(r, BATCH)) expect(row.lines.length).toBeGreaterThan(0);
    }
  });
});
