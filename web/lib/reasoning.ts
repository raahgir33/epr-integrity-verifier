// Shapes of ReasoningStepOut.output per step_type, from
// api/app/models/agent.py and api/app/store/cache.py's _compute_reasoning_
// steps/score-step construction — the OpenAPI schema types `output` as a
// loose object (it varies by step_type), so these are hand-written to match
// the real backend shapes, not generated.

import type { ReasoningStepOut } from "@/lib/api";

export type HypothesisConclusion = {
  certificate_batch: string;
  status: "supported" | "partly_supported" | "unsupported";
  evidence_ids: string[];
  explanation: string;
};

export type ProposedFinding = {
  finding_type: string;
  effect: "raises_concern" | "resolves_concern";
  cited_shipment_ids: string[];
  evidence_ids: string[];
  explanation: string;
};

export type HypothesisOutput = {
  conclusions: HypothesisConclusion[];
  findings: ProposedFinding[];
};

export type CriticVerdict = {
  hypothesis_finding_index: number;
  verdict: "upheld" | "disputed";
  reason: string;
};

export type CriticFinalOutput = {
  verdicts: CriticVerdict[];
  objections: ProposedFinding[];
};

export type RevisionDecision = {
  objection_index: number;
  accepted: boolean;
  explanation: string;
};

export type HypothesisFindingResponse = {
  hypothesis_finding_index: number;
  decision: "maintain" | "withdraw";
  explanation: string;
};

export type RevisionOutput =
  | { note: string }
  | { revisions: RevisionDecision[]; hypothesis_finding_responses: HypothesisFindingResponse[] };

export type DeductedShipment = { shipment_id: string; weighbridge_net_t: number | null };

export type ScoreOutput = {
  checks_only_verifiable_t: number | null;
  full_verifiable_t: number | null;
  deducted_shipments: DeductedShipment[];
  risk_band_before: string | null;
  risk_band_after: string | null;
};

// ---------- T13.5b plan, Part 4: reasoning log panel ----------

/** The log panel's agent tag — the brief names exactly Hypothesis/Critic/
 * Revision/Tool, but `score` is deterministic Python (the internal
 * engineering notes' "the language model never does arithmetic that
 * matters"), not agent output —
 * folding it into "Revision" would misattribute a computed number to an
 * agent, so it gets its own neutral "Score" tag instead. `tool_cap_reached`
 * folds into "Tool" (it's a tool-loop meta-event, not a new agent). */
export type StepTag = "Hypothesis" | "Critic" | "Revision" | "Tool" | "Score";

const STEP_TAG: Record<string, StepTag> = {
  hypothesis: "Hypothesis",
  critic_tool: "Tool",
  tool_cap_reached: "Tool",
  critic_final: "Critic",
  critic_model_turn: "Critic",
  revision: "Revision",
  score: "Score",
};

export function stepTag(step: ReasoningStepOut): StepTag {
  return STEP_TAG[step.step_type] ?? "Tool";
}

/** One-line action description for the log's always-visible row (distinct
 * from ReasoningTimeline's existing per-type "gist", which this reuses
 * where it already reads as an action). */
/** T16c F19: "1 verdict(s)" was reaching the screen. Count plus the right
 * noun form; the irregular plural is passed in where "+s" is wrong. */
function plural(count: number, singular: string, pluralForm?: string): string {
  return `${count} ${count === 1 ? singular : (pluralForm ?? `${singular}s`)}`;
}

export function stepActionLine(step: ReasoningStepOut): string {
  switch (step.step_type) {
    case "hypothesis": {
      const output = step.output as unknown as HypothesisOutput | undefined;
      return output
        ? `Judged ${plural(output.conclusions.length, "certificate batch", "certificate batches")}, proposed ${plural(output.findings.length, "finding")}`
        : "Judged the certificate batches";
    }
    case "critic_tool":
      return step.dedup_hit ? `Reused an earlier ${step.tool_name} call` : `Called ${step.tool_name}`;
    case "tool_cap_reached":
      return "Reached its maximum tool calls for this run";
    case "critic_final": {
      const output = step.output as unknown as CriticFinalOutput | undefined;
      return output
        ? `Issued ${plural(output.verdicts.length, "verdict")} and ${plural(output.objections.length, "objection")}`
        : "Issued its final objections";
    }
    case "critic_model_turn":
      return "Reasoned over the dossier before its next tool call";
    case "revision": {
      const output = step.output as unknown as RevisionOutput | undefined;
      if (output && "revisions" in output) {
        const accepted = output.revisions.filter((r) => r.accepted).length;
        return `Accepted ${accepted} of ${plural(output.revisions.length, "Critic objection")}`;
      }
      return "Revised its findings";
    }
    case "score": {
      const output = step.output as unknown as ScoreOutput | undefined;
      return output
        ? `Computed the risk band — ${output.risk_band_before ?? "—"} → ${output.risk_band_after ?? "—"}`
        : "Computed the risk band";
    }
    default:
      return step.step_type;
  }
}
