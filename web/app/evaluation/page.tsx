import type { Metadata } from "next";
import { EmptyState } from "@/components/EmptyState";
import { AccuracyComparisonChart } from "@/components/evaluation/AccuracyComparisonChart";
import { BandStabilityChart } from "@/components/evaluation/BandStabilityChart";
import { DetectionMatrixChart } from "@/components/evaluation/DetectionMatrixChart";
import { ProcessorErrorChart } from "@/components/evaluation/ProcessorErrorChart";
import { StatCard } from "@/components/StatCard";
import { Heading } from "@/components/ui/Heading";
import { getEvaluation } from "@/lib/api";
import {
  accuracyComparison,
  annotateMisses,
  bandStability,
  detectionMatrix,
  extractedGapNote,
  groupMetrics,
  processorErrors,
  summaryFigures,
  type SummaryFigure,
} from "@/lib/evaluation";

export const metadata: Metadata = {
  title: "Evaluation",
  description: "Extraction accuracy and detection precision/recall against a held-out, seeded ground truth.",
};

/** The four headline figures, every one derived from this dataset's own
 * eval_metrics rows (lib/evaluation.ts's summaryFigures) — a figure whose
 * rows are missing is omitted upstream rather than shown as "n/a". */
function SummaryRow({ figures, note }: { figures: SummaryFigure[]; note?: string | null }) {
  if (figures.length === 0) return null;
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {figures.map((f) => (
          <StatCard key={f.key} label={f.label} value={f.display} sub={f.sub} />
        ))}
      </div>
      {note ? <p className="text-xs leading-relaxed text-ink-muted">{note}</p> : null}
    </div>
  );
}

export default async function EvaluationPage() {
  const evaluation = await getEvaluation();
  const heldoutGroups = groupMetrics(evaluation.heldout);
  const heldoutSummary = summaryFigures(evaluation.heldout);
  const devSummary = summaryFigures(evaluation.dev);
  // Each chart's rows are read straight from this dataset's own
  // eval_metrics rows, and each selector returns null when its rows are
  // absent — a chart with no data is omitted, never rendered as "n/a".
  const comparison = accuracyComparison(evaluation.heldout);
  const errors = processorErrors(evaluation.heldout);
  const detection = detectionMatrix(evaluation.heldout);
  const stability = bandStability(evaluation.heldout);
  const misses = annotateMisses(
    evaluation.misses,
    evaluation.heldout,
    evaluation.heldout_dataset_label
  );

  return (
    <div className="space-y-8">
      <div className="text-center">
        <Heading>Evaluation</Heading>
        <p className="mx-auto mt-1 max-w-[70ch] text-pretty text-sm text-ink-muted tracking-wide leading-loose">
          Extraction Accuracy and Detection Precision/Recall Against a Held-Out, Seeded Ground Truth.
          See <a href="/method" className="underline decoration-dotted hover:text-primary">Method</a> for the Protocol.
        </p>
      </div>

      {!evaluation.available ? (
        <EmptyState title="Not yet available" message={evaluation.message ?? "Evaluation metrics are not yet available."} />
      ) : (
        <section className="space-y-6">
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="font-display text-xl tracking-wide font-semibold text-ink">Held-Out Testing Dataset</h2>
            <span className="text-xs text-ink-muted">{evaluation.heldout_dataset_label}</span>
          </div>

          <SummaryRow figures={heldoutSummary} note={extractedGapNote(evaluation.heldout)} />

          {comparison ? <AccuracyComparisonChart comparison={comparison} /> : null}
          {errors ? <ProcessorErrorChart errors={errors} /> : null}
          {detection ? <DetectionMatrixChart matrix={detection} /> : null}
          {stability ? <BandStabilityChart stability={stability} /> : null}

          {heldoutGroups.map(({ group, metrics }) => (
            <div key={group} className="space-y-2">
              <h3 className="text-xs font-medium uppercase tracking-wide text-ink-muted">{group}</h3>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {metrics.map((m) => (
                  <StatCard key={m.metric} label={m.label} value={m.display} sub={m.sub} />
                ))}
              </div>
            </div>
          ))}
          {misses.length > 0 ? (
            <div className="card p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">Misses</p>
              <ul className="mt-2 space-y-1.5 text-sm text-ink">
                {misses.map((miss) => (
                  <li key={miss} className="border-l-2 border-risk-high/60 pl-2 text-ink-muted">
                    {miss}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-sm text-ink-muted">No misses: every planted pattern was detected and no clean or hard-negative processor was wrongly flagged.</p>
          )}
        </section>
      )}

      {devSummary.length > 0 ? (
        <section className="space-y-3 border-t border-border pt-6">
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="font-display text-base font-medium text-ink-muted">
              Development set (rules tuned on it)
            </h2>
            <span className="text-xs text-ink-muted">{evaluation.dev_dataset_label}</span>
          </div>
          <p className="text-xs text-ink-muted">
            Shown for reference only — these numbers come from the same dataset the rule thresholds and
            prompts were tuned against, so they are not evidence of real-world accuracy.
          </p>
          <SummaryRow figures={devSummary} note={extractedGapNote(evaluation.dev)} />
          <p className="text-xs text-ink-muted">
            Only these headline figures are measured on the development set. Run-to-run stability,
            cost, latency, finding precision and false-flag rates are not run on the development set:
            measuring them would need fresh extracted-facts agent runs.
          </p>
        </section>
      ) : null}
    </div>
  );
}
