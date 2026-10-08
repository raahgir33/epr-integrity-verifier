import { EvidenceList } from "@/components/EvidenceLink";
import type { CheckResultOut } from "@/lib/api";
import { formatCheckValue, STATUS_LABEL, STATUS_TONE } from "@/lib/checks";

export function CheckResultRow({
  check,
  knownDocIds,
}: {
  check: CheckResultOut;
  knownDocIds: ReadonlySet<string>;
}) {
  return (
    <li className="border-b border-slate-100 py-3 last:border-0">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-mono text-sm font-semibold text-slate-900">{check.check_id}</span>
        <span className={`text-sm font-medium ${STATUS_TONE[check.status] ?? "text-slate-500"}`}>
          {STATUS_LABEL[check.status] ?? check.status}
        </span>
        <span className="text-xs uppercase tracking-wide text-slate-400">{check.severity}</span>
      </div>
      <p className="mt-1 text-sm text-slate-600">
        Measured {formatCheckValue(check.check_id, check.measured)} · Threshold{" "}
        {formatCheckValue(check.check_id, check.threshold)}{" "}
        <span className="text-slate-400">({check.source})</span>
      </p>
      <p className="mt-1 text-sm text-slate-700">{check.explanation}</p>
      {check.evidence_ids.length > 0 ? (
        <div className="mt-1.5 text-xs">
          <span className="mr-1.5 font-medium text-slate-500">Evidence:</span>
          <EvidenceList evidenceIds={check.evidence_ids} knownDocIds={knownDocIds} />
        </div>
      ) : null}
    </li>
  );
}
