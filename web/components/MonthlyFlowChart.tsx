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
import { useChartColors } from "@/lib/useChartColors";

export function MonthlyFlowChart({ rows }: { rows: MonthlyFlowRow[] }) {
  const colors = useChartColors();
  const data = rows.map((row) => ({
    month: formatMonth(row.month),
    "Certified (t)": row.certified_t,
    "Verified inbound (t)": row.verified_inbound_t,
  }));

  return (
    <div className="h-126 w-full pt-9">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke={colors.grid} vertical={false} />
          <XAxis dataKey="month" tick={{ fontSize: 12, fill: colors.axisText }} />
          <YAxis
            tick={{ fontSize: 12, fill: colors.axisText }}
            tickFormatter={(value: number) => value.toLocaleString("en-IN")}
            width={64}
          />
          <Tooltip formatter={(value) => formatTonnes(Number(value))} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="Certified (t)" fill={colors.certifiedBar} radius={[2, 2, 0, 0]} />
          <Line
            type="monotone"
            dataKey="Verified inbound (t)"
            stroke={colors.verifiedLine}
            strokeWidth={2}
            dot={{ r: 3 }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
