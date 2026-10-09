"use client";

import { ReasoningLog } from "@/components/reasoning/ReasoningLog";
import type { ReasoningStepOut } from "@/lib/api";

/** Thin wrapper (T13.5b plan, Part 4) — kept so ProcessorTabs' sub-xl
 * "Agent Reasoning" tab and RunProgress's live trail don't need to change
 * imports; the actual log-style rendering (newest first, tag dots,
 * expand animation) lives in ReasoningLog. Per-step-type detail blocks
 * live in StepDetail.tsx, shared by both. */
export function ReasoningTimeline(props: {
  steps: ReasoningStepOut[];
  knownDocIds: ReadonlySet<string>;
  isLive?: boolean;
}) {
  return <ReasoningLog {...props} />;
}
