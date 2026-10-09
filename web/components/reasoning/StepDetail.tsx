import { EvidenceList } from "@/components/EvidenceLink";
import { HypothesisStep } from "@/components/reasoning/HypothesisStep";
import { ToolStep } from "@/components/reasoning/ToolStep";
import type { ReasoningStepOut } from "@/lib/api";
import { formatSignedTonnes, formatTonnes } from "@/lib/format";
import type { CriticFinalOutput, HypothesisOutput, RevisionOutput, ScoreOutput } from "@/lib/reasoning";

/** Per-step-type detail block, shared by ReasoningLog (the panel) and
 * anything that needs to render a single step's expanded content — split
 * into its own module so ReasoningLog.tsx and ReasoningTimeline.tsx (a
 * thin wrapper around it) don't import each other. */

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

export function StepDetail({ step, knownDocIds }: { step: ReasoningStepOut; knownDocIds: ReadonlySet<string> }) {
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
