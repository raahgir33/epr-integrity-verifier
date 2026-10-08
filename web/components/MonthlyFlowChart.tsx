"use client";

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { MonthlyFlowRow } from "@/lib/api";
import { formatMonth, formatTonnes } from "@/lib/format";

export function MonthlyFlowChart({ rows }: { rows: MonthlyFlowRow[] }) {
  const data = rows.map((row) => ({
    month: formatMonth(row.month),
    "Certified (t)": row.certified_t,
    "Verified inbound (t)": row.verified_inbound_t,
  }));

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#e2e8f0" vertical={false} />
          <XAxis dataKey="month" tick={{ fontSize: 12, fill: "#475569" }} />
          <YAxis
            tick={{ fontSize: 12, fill: "#475569" }}
            tickFormatter={(value: number) => value.toLocaleString("en-IN")}
            width={64}
          />
          <Tooltip formatter={(value) => formatTonnes(Number(value))} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="Certified (t)" fill="#94a3b8" radius={[2, 2, 0, 0]} />
          <Line
            type="monotone"
            dataKey="Verified inbound (t)"
            stroke="#0f172a"
            strokeWidth={2}
            dot={{ r: 3 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
