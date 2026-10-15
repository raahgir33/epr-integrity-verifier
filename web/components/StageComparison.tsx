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
    <div className="card overflow-x-auto p-4">
      <table className="w-full min-w-[28rem] border-collapse text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-ink-muted">
            <th className="py-2 pr-4 font-medium">Measure</th>
            <th className="py-2 pr-4 text-right font-medium">Rule Checks</th>
            {/* T16c F26: the raw status string used to render straight
                into the header as "AGENT VALIDATION (OK)". */}
            <th className="py-2 text-right font-medium">
              Agent Validation {agentStatus === "ok" ? "(complete)" : agentStatus ? `(${agentStatus})` : "(not yet run)"}
            </th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map(({ key, label }) => (
            <tr key={key} className="border-b border-border last:border-0">
              <td className="py-2 pr-4 text-ink-muted">{label}</td>
              <td className="num-cell py-2 pr-4 tabular-nums">{formatTonnes(checksOnly[key] as number)}</td>
              <td className="num-cell py-2 tabular-nums">
                {full ? formatTonnes(full[key] as number) : "—"}
              </td>
            </tr>
          ))}
          <tr>
            <td className="py-2 pr-4 text-ink-muted">Risk band</td>
            <td className="py-2 pr-4 text-right">
              <RiskBadge band={checksOnly.risk_band} />
            </td>
            <td className="py-2 text-right">{full ? <RiskBadge band={full.risk_band} /> : "—"}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
