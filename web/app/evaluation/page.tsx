import { EmptyState } from "@/components/EmptyState";
import { getEvaluation } from "@/lib/api";

export default async function EvaluationPage() {
  const evaluation = await getEvaluation();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold text-slate-900">Evaluation</h1>
        <p className="mt-1 text-sm text-slate-600">
          Extraction accuracy and detection precision/recall against a held-out, seeded ground truth —
          see <a href="/method" className="underline decoration-dotted">Method</a> for the protocol.
        </p>
      </div>

      {evaluation.available ? null : (
        <EmptyState title="Not yet available" message={evaluation.message ?? "Evaluation metrics are not yet available."} />
      )}
    </div>
  );
}
