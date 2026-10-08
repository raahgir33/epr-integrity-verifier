import { EvidenceList } from "@/components/EvidenceLink";
import type { FindingOut } from "@/lib/api";
import { agreementLabel, classificationLabel, originLabel } from "@/lib/findings";

export function FindingCard({
  finding,
  knownDocIds,
}: {
  finding: FindingOut;
  knownDocIds: ReadonlySet<string>;
}) {
  return (
    <li className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-700">
          {agreementLabel(finding)}
        </span>
        <span className="text-slate-500">{originLabel(finding)}</span>
      </div>
      <p className="mt-2 text-sm text-slate-900">{finding.finding_type}</p>
      <p className="mt-1 text-sm text-slate-600">{finding.explanation}</p>
      <p className="mt-2 text-xs font-medium text-slate-500">{classificationLabel(finding)}</p>

      {finding.cited_shipment_ids.length > 0 ? (
        <div className="mt-3 text-xs">
          <span className="font-medium text-slate-500">Shipments: </span>
          <span className="font-mono text-slate-700">{finding.cited_shipment_ids.join(", ")}</span>
        </div>
      ) : null}

      {finding.evidence_ids.length > 0 ? (
        <div className="mt-2 text-xs">
          <span className="mr-1.5 font-medium text-slate-500">Evidence:</span>
          <EvidenceList evidenceIds={finding.evidence_ids} knownDocIds={knownDocIds} />
        </div>
      ) : null}

      {finding.verdict ? (
        <p className="mt-2 text-xs text-slate-500">
          Critic verdict: <span className="font-medium">{finding.verdict.verdict}</span> —{" "}
          {finding.verdict.reason}
        </p>
      ) : null}
      {finding.disputed_by ? (
        <p className="mt-1 text-xs text-slate-500">
          Hypothesis {finding.disputed_by.decision}: {finding.disputed_by.explanation}
        </p>
      ) : null}
    </li>
  );
}
