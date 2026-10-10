import type { Metadata } from "next";
import { EmptyState } from "@/components/EmptyState";
import { StatCard } from "@/components/StatCard";
import { Heading } from "@/components/ui/Heading";
import { getEvaluation } from "@/lib/api";
import { annotateMisses, groupMetrics } from "@/lib/evaluation";

export const metadata: Metadata = {
  title: "Evaluation",
  description: "Extraction accuracy and detection precision/recall against a held-out, seeded ground truth.",
};

export default async function EvaluationPage() {
  const evaluation = await getEvaluation();
  const heldoutGroups = groupMetrics(evaluation.heldout);
  const devGroups = groupMetrics(evaluation.dev);
  const misses = annotateMisses(evaluation.misses, evaluation.heldout);

  return (
    <div className="space-y-8">
      <div className="text-center">
        <Heading>Evaluation</Heading>
        <p className="mx-auto mt-1 max-w-[70ch] text-pretty text-sm text-ink-muted">
          Extraction accuracy and detection precision/recall against a held-out, seeded ground truth.
          See <a href="/method" className="underline decoration-dotted hover:text-primary">Method</a> for the protocol.
        </p>
      </div>

      {!evaluation.available ? (
        <EmptyState title="Not yet available" message={evaluation.message ?? "Evaluation metrics are not yet available."} />
      ) : (
        <section className="space-y-6">
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="font-display text-lg font-semibold text-ink">Held-out test set</h2>
            <span className="text-xs text-ink-muted">{evaluation.heldout_dataset_label}</span>
          </div>

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
        </section>
      )}

      {devGroups.length > 0 ? (
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
          {devGroups.map(({ group, metrics }) => (
            <div key={group} className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {metrics.map((m) => (
                <StatCard key={m.metric} label={m.label} value={m.display} sub={m.sub} />
              ))}
            </div>
          ))}
        </section>
      ) : null}
    </div>
  );
}
