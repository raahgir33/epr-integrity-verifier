import { RiskBadge } from "@/components/RiskBadge";
import type { StageAssessment } from "@/lib/api";
import { formatTonnes } from "@/lib/format";

const ROWS: { key: keyof StageAssessment; label: string }[] = [
  { key: "certified_t", label: "Certified" },
  { key: "verified_inbound_t", label: "Verified inbound" },
  { key: "capacity_limit_t", label: "Capacity limit" },
  { key: "verifiable_t", label: "Verifiable" },
  { key: "unverifiable_t", label: "Unverifiable" },
];

export function StageComparison({
  checksOnly,
  full,
  agentStatus,
}: {
  checksOnly: StageAssessment;
  full: StageAssessment | null;
  agentStatus: string | null;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[28rem] border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="py-2 pr-4 font-medium">Measure</th>
            <th className="py-2 pr-4 font-medium">Checks-only</th>
            <th className="py-2 font-medium">
              With agents {agentStatus ? `(${agentStatus})` : "(not yet run)"}
            </th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map(({ key, label }) => (
            <tr key={key} className="border-b border-slate-100 last:border-0">
              <td className="py-2 pr-4 text-slate-600">{label}</td>
              <td className="num-cell py-2 pr-4 tabular-nums">{formatTonnes(checksOnly[key] as number)}</td>
              <td className="num-cell py-2 tabular-nums">
                {full ? formatTonnes(full[key] as number) : "—"}
              </td>
            </tr>
          ))}
          <tr>
            <td className="py-2 pr-4 text-slate-600">Risk band</td>
            <td className="py-2 pr-4">
              <RiskBadge band={checksOnly.risk_band} />
            </td>
            <td className="py-2">{full ? <RiskBadge band={full.risk_band} /> : "—"}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
