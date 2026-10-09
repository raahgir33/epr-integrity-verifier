"use client";

import { useState } from "react";
import { EvidenceList } from "@/components/EvidenceLink";
import { HypothesisStep } from "@/components/reasoning/HypothesisStep";
import { ToolStep } from "@/components/reasoning/ToolStep";
import type { ReasoningStepOut } from "@/lib/api";
import { formatSignedTonnes, formatTonnes } from "@/lib/format";
import type {
  CriticFinalOutput,
  HypothesisOutput,
  RevisionOutput,
  ScoreOutput,
} from "@/lib/reasoning";

const STEP_LABEL: Record<string, string> = {
  hypothesis: "Hypothesis",
  critic_tool: "Critic — tool call",
  critic_final: "Critic — final objections",
  critic_model_turn: "Critic",
  revision: "Revision",
  score: "Score",
  tool_cap_reached: "Tool call limit reached",
};

/** One-line gist shown even while a step is collapsed (T13.5 plan, Part
 * 4 — "collapsed per step with expand"), independent of each step
 * type's own detailed block below. */
function stepGist(step: ReasoningStepOut): string | null {
  switch (step.step_type) {
    case "hypothesis": {
      const output = step.output as unknown as HypothesisOutput | undefined;
      return output ? `${output.conclusions.length} conclusion(s), ${output.findings.length} finding(s)` : null;
    }
    case "critic_tool":
      return step.tool_name;
    case "critic_final": {
      const output = step.output as unknown as CriticFinalOutput | undefined;
      return output
        ? `${output.verdicts.length} verdict(s), ${output.objections.length} objection(s)`
        : null;
    }
    case "score": {
      const output = step.output as unknown as ScoreOutput | undefined;
      return output ? `Risk band ${output.risk_band_before ?? "—"} → ${output.risk_band_after ?? "—"}` : null;
    }
    default:
      return null;
  }
}

function CriticFinalBlock({
  output,
  knownDocIds,
}: {
  output: CriticFinalOutput;
  knownDocIds: ReadonlySet<string>;
}) {
  if (output.objections.length === 0 && output.verdicts.length === 0) {
    return <p className="text-sm text-ink-muted">No new objections, no verdicts on Hypothesis findings.</p>;
  }
  return (
    <div className="space-y-2 text-sm">
      {output.verdicts.map((v, i) => (
        <p key={i} className="text-ink-muted">
          Verdict on Hypothesis finding #{v.hypothesis_finding_index + 1}:{" "}
          <span className="font-medium">{v.verdict}</span> — {v.reason}
        </p>
      ))}
      {output.objections.map((o, i) => (
        <div key={i}>
          <p className="font-medium text-ink">{o.finding_type}</p>
          <p className="text-ink-muted">{o.explanation}</p>
          {o.evidence_ids.length > 0 ? (
            <div className="mt-0.5">
              <EvidenceList evidenceIds={o.evidence_ids} knownDocIds={knownDocIds} />
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function RevisionBlock({ output }: { output: RevisionOutput }) {
  if ("note" in output) {
    return <p className="text-sm text-ink-muted">{output.note}</p>;
  }
  return (
    <div className="space-y-1 text-sm text-ink-muted">
      {output.revisions.map((r, i) => (
        <p key={`r${i}`}>
          Critic finding #{r.objection_index + 1}: {r.accepted ? "accepted" : "rejected"} — {r.explanation}
        </p>
      ))}
      {output.hypothesis_finding_responses.map((r, i) => (
        <p key={`h${i}`}>
          Hypothesis finding #{r.hypothesis_finding_index + 1}: {r.decision} — {r.explanation}
        </p>
      ))}
    </div>
  );
}

function ScoreBlock({ output }: { output: ScoreOutput }) {
  return (
    <div className="text-sm text-ink-muted">
      <p>
        Rule Checks verifiable: {output.checks_only_verifiable_t !== null ? formatTonnes(output.checks_only_verifiable_t) : "—"}
        {" → "}
        Agent Validation: {output.full_verifiable_t !== null ? formatTonnes(output.full_verifiable_t) : "—"}
      </p>
      <p>
        Risk band: {output.risk_band_before ?? "—"} → {output.risk_band_after ?? "—"}
      </p>
      {output.deducted_shipments.length > 0 ? (
        <div className="mt-1">
          <span className="font-medium text-ink-muted">Deducted shipments:</span>{" "}
          {output.deducted_shipments.map((s) => (
            <span key={s.shipment_id} className="mr-2 font-mono text-xs">
              {s.shipment_id}
              {s.weighbridge_net_t !== null ? ` (${formatSignedTonnes(-s.weighbridge_net_t)})` : ""}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function StepDetail({ step, knownDocIds }: { step: ReasoningStepOut; knownDocIds: ReadonlySet<string> }) {
  if (step.step_type === "hypothesis" && step.output) {
    return <HypothesisStep output={step.output as unknown as HypothesisOutput} knownDocIds={knownDocIds} />;
  }
  if (step.step_type === "critic_tool") {
    return <ToolStep step={step} knownDocIds={knownDocIds} />;
  }
  if (step.step_type === "critic_final" && step.output) {
    return <CriticFinalBlock output={step.output as unknown as CriticFinalOutput} knownDocIds={knownDocIds} />;
  }
  if (step.step_type === "revision" && step.output) {
    return <RevisionBlock output={step.output as unknown as RevisionOutput} />;
  }
  if (step.step_type === "score" && step.output) {
    return <ScoreBlock output={step.output as unknown as ScoreOutput} />;
  }
  if (step.step_type === "tool_cap_reached") {
    return <p className="text-sm text-ink-muted">The Critic reached its maximum tool calls for this run.</p>;
  }
  if (step.step_type === "critic_model_turn") {
    return <p className="text-sm text-ink-muted">Intermediate Critic model turn.</p>;
  }
  return null;
}

function StepRow({ step, knownDocIds }: { step: ReasoningStepOut; knownDocIds: ReadonlySet<string> }) {
  const [open, setOpen] = useState(false);
  const gist = stepGist(step);

  return (
    <li className="flex gap-3">
      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-sunk text-xs font-medium text-ink-muted">
        {step.step_index + 1}
      </span>
      <div className="min-w-0 flex-1">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex w-full items-center justify-between gap-2 text-left"
        >
          <span>
            <span className="text-xs font-medium uppercase tracking-wide text-ink-muted">
              {STEP_LABEL[step.step_type] ?? step.step_type}
            </span>
            {!open && gist ? <span className="ml-2 text-sm text-ink-muted">{gist}</span> : null}
          </span>
          <svg
            viewBox="0 0 16 16"
            aria-hidden
            className={`h-4 w-4 shrink-0 text-ink-muted transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          >
            <path
              d="M4 6l4 4 4-4"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
        {open ? (
          <div className="mt-1">
            <StepDetail step={step} knownDocIds={knownDocIds} />
            {step.latency_ms !== null || step.tokens ? (
              <p className="mt-1 text-[11px] text-ink-muted">
                {step.latency_ms !== null ? `${Math.round(step.latency_ms)} ms` : null}
                {step.tokens && Object.values(step.tokens).some((v) => v !== null)
                  ? ` · ${Object.entries(step.tokens)
                      .filter(([, v]) => v !== null)
                      .map(([k, v]) => `${k} ${v}`)
                      .join(", ")}`
                  : null}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </li>
  );
}

export function ReasoningTimeline({
  steps,
  knownDocIds,
}: {
  steps: ReasoningStepOut[];
  knownDocIds: ReadonlySet<string>;
}) {
  if (steps.length === 0) {
    return <p className="text-sm text-ink-muted">No agent run has happened for this processor yet.</p>;
  }

  return (
    <ol className="space-y-3">
      {steps.map((step) => (
        <StepRow key={step.step_index} step={step} knownDocIds={knownDocIds} />
      ))}
    </ol>
  );
}
