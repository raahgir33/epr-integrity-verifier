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

function CriticFinalBlock({
  output,
  knownDocIds,
}: {
  output: CriticFinalOutput;
  knownDocIds: ReadonlySet<string>;
}) {
  if (output.objections.length === 0 && output.verdicts.length === 0) {
    return <p className="text-sm text-slate-500">No new objections, no verdicts on Hypothesis findings.</p>;
  }
  return (
    <div className="space-y-2 text-sm">
      {output.verdicts.map((v, i) => (
        <p key={i} className="text-slate-600">
          Verdict on Hypothesis finding #{v.hypothesis_finding_index + 1}:{" "}
          <span className="font-medium">{v.verdict}</span> — {v.reason}
        </p>
      ))}
      {output.objections.map((o, i) => (
        <div key={i}>
          <p className="font-medium text-slate-900">{o.finding_type}</p>
          <p className="text-slate-600">{o.explanation}</p>
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
    return <p className="text-sm text-slate-500">{output.note}</p>;
  }
  return (
    <div className="space-y-1 text-sm text-slate-600">
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
    <div className="text-sm text-slate-600">
      <p>
        Checks-only verifiable: {output.checks_only_verifiable_t !== null ? formatTonnes(output.checks_only_verifiable_t) : "—"}
        {" → "}
        With agents: {output.full_verifiable_t !== null ? formatTonnes(output.full_verifiable_t) : "—"}
      </p>
      <p>
        Risk band: {output.risk_band_before ?? "—"} → {output.risk_band_after ?? "—"}
      </p>
      {output.deducted_shipments.length > 0 ? (
        <div className="mt-1">
          <span className="font-medium text-slate-500">Deducted shipments:</span>{" "}
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

export function ReasoningTimeline({
  steps,
  knownDocIds,
}: {
  steps: ReasoningStepOut[];
  knownDocIds: ReadonlySet<string>;
}) {
  if (steps.length === 0) {
    return <p className="text-sm text-slate-500">No agent run has happened for this processor yet.</p>;
  }

  return (
    <ol className="space-y-4">
      {steps.map((step) => (
        <li key={step.step_index} className="flex gap-3">
          <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-medium text-slate-600">
            {step.step_index + 1}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
              {STEP_LABEL[step.step_type] ?? step.step_type}
            </p>
            <div className="mt-1">
              {step.step_type === "hypothesis" && step.output ? (
                <HypothesisStep output={step.output as unknown as HypothesisOutput} knownDocIds={knownDocIds} />
              ) : null}
              {step.step_type === "critic_tool" ? <ToolStep step={step} knownDocIds={knownDocIds} /> : null}
              {step.step_type === "critic_final" && step.output ? (
                <CriticFinalBlock
                  output={step.output as unknown as CriticFinalOutput}
                  knownDocIds={knownDocIds}
                />
              ) : null}
              {step.step_type === "revision" && step.output ? (
                <RevisionBlock output={step.output as unknown as RevisionOutput} />
              ) : null}
              {step.step_type === "score" && step.output ? (
                <ScoreBlock output={step.output as unknown as ScoreOutput} />
              ) : null}
              {step.step_type === "tool_cap_reached" ? (
                <p className="text-sm text-slate-500">
                  The Critic reached its maximum tool calls for this run.
                </p>
              ) : null}
              {step.step_type === "critic_model_turn" ? (
                <p className="text-sm text-slate-500">Intermediate Critic model turn.</p>
              ) : null}
            </div>
            {(step.latency_ms !== null || step.tokens) ? (
              <p className="mt-1 text-[11px] text-slate-400">
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
        </li>
      ))}
    </ol>
  );
}
