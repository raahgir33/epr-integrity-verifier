"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { RiskBadge } from "@/components/RiskBadge";
import type { ProcessorSummary } from "@/lib/api";
import { formatSignedTonnes, formatTonnes } from "@/lib/format";

type SortKey = "certified" | "checksOnly" | "withAgents" | "delta" | "risk";

const RISK_ORDER: Record<string, number> = { Low: 0, Medium: 1, High: 2 };

function withAgentsVerifiable(p: ProcessorSummary): number {
  return p.full ? p.full.verifiable_t : p.checks_only.verifiable_t;
}

function delta(p: ProcessorSummary): number {
  return p.full ? p.full.verifiable_t - p.checks_only.verifiable_t : 0;
}

function sortValue(p: ProcessorSummary, key: SortKey): number {
  switch (key) {
    case "certified":
      return p.checks_only.certified_t;
    case "checksOnly":
      return p.checks_only.verifiable_t;
    case "withAgents":
      return withAgentsVerifiable(p);
    case "delta":
      return delta(p);
    case "risk":
      return RISK_ORDER[(p.full ?? p.checks_only).risk_band] ?? -1;
    default:
      return 0;
  }
}

function HeaderButton({
  label,
  sortKey,
  active,
  dir,
  onClick,
}: {
  label: string;
  sortKey: SortKey;
  active: boolean;
  dir: "asc" | "desc";
  onClick: (key: SortKey) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onClick(sortKey)}
      className="flex items-center gap-1 font-medium text-slate-500 hover:text-slate-900"
    >
      {label}
      {active ? <span aria-hidden>{dir === "asc" ? "↑" : "↓"}</span> : null}
    </button>
  );
}

export function ProcessorsTable({ processors }: { processors: ProcessorSummary[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("delta");
  const [dir, setDir] = useState<"asc" | "desc">("desc");

  const sorted = useMemo(() => {
    const copy = [...processors];
    copy.sort((a, b) => (sortValue(a, sortKey) - sortValue(b, sortKey)) * (dir === "asc" ? 1 : -1));
    return copy;
  }, [processors, sortKey, dir]);

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setDir("desc");
    }
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[48rem] border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide">
            <th className="py-2 pr-4 font-medium text-slate-500">Processor</th>
            <th className="py-2 pr-4 font-medium text-slate-500">Type</th>
            <th className="py-2 pr-4">
              <HeaderButton label="Certified" sortKey="certified" active={sortKey === "certified"} dir={dir} onClick={handleSort} />
            </th>
            <th className="py-2 pr-4">
              <HeaderButton label="Checks-only" sortKey="checksOnly" active={sortKey === "checksOnly"} dir={dir} onClick={handleSort} />
            </th>
            <th className="py-2 pr-4">
              <HeaderButton label="With agents" sortKey="withAgents" active={sortKey === "withAgents"} dir={dir} onClick={handleSort} />
            </th>
            <th className="py-2 pr-4">
              <HeaderButton label="Δ" sortKey="delta" active={sortKey === "delta"} dir={dir} onClick={handleSort} />
            </th>
            <th className="py-2 pr-4">
              <HeaderButton label="Risk" sortKey="risk" active={sortKey === "risk"} dir={dir} onClick={handleSort} />
            </th>
            <th className="py-2 font-medium text-slate-500">Agent</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((p) => {
            const d = delta(p);
            return (
              <tr key={p.processor_id} className="border-b border-slate-100 last:border-0">
                <td className="py-2 pr-4">
                  <Link
                    href={`/processors/${encodeURIComponent(p.processor_id)}`}
                    className="font-medium text-slate-900 underline decoration-dotted hover:text-slate-700"
                  >
                    {p.processor_id}
                  </Link>
                  <div className="text-xs text-slate-500">{p.name}</div>
                </td>
                <td className="py-2 pr-4 text-slate-600">{p.type}</td>
                <td className="num-cell py-2 pr-4 tabular-nums">{formatTonnes(p.checks_only.certified_t)}</td>
                <td className="num-cell py-2 pr-4 tabular-nums">{formatTonnes(p.checks_only.verifiable_t)}</td>
                <td className="num-cell py-2 pr-4 tabular-nums">{formatTonnes(withAgentsVerifiable(p))}</td>
                <td className="py-2 pr-4">
                  <div className="num-cell tabular-nums">
                    {d > 0 ? <span className="text-risk-low">{formatSignedTonnes(d)}</span> : formatSignedTonnes(0)}
                  </div>
                  {d > 0 && p.agent_status === "ok" ? (
                    <div className="mt-0.5 text-right text-[11px] font-medium text-risk-low">
                      agents found {formatTonnes(d)}
                    </div>
                  ) : null}
                </td>
                <td className="py-2 pr-4">
                  <RiskBadge band={(p.full ?? p.checks_only).risk_band} />
                </td>
                <td className="py-2 text-xs text-slate-500">{p.agent_status ?? "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
