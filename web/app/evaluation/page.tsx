import { EmptyState } from "@/components/EmptyState";
import { Heading } from "@/components/ui/Heading";
import { getEvaluation } from "@/lib/api";

export default async function EvaluationPage() {
  const evaluation = await getEvaluation();

  return (
    <div className="space-y-6">
      <div>
        <Heading>Evaluation</Heading>
        <p className="mt-1 max-w-[70ch] text-pretty text-sm text-ink-muted">
          Extraction accuracy and detection precision/recall against a held-out, seeded ground truth —
          see <a href="/method" className="underline decoration-dotted hover:text-primary">Method</a> for the protocol.
        </p>
      </div>

      {evaluation.available ? null : (
        <EmptyState title="Not yet available" message={evaluation.message ?? "Evaluation metrics are not yet available."} />
      )}
    </div>
  );
}
