"use client";

import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { MonthlyFlowRow } from "@/lib/api";
import { formatMonth, formatTonnes } from "@/lib/format";
import { useChartColors, type ChartColors } from "@/lib/useChartColors";

const CERTIFIED = "Certified (t)";
const VERIFIED = "Verified inbound (t)";

type FlowPoint = {
  month: string;
  [CERTIFIED]: number;
  [VERIFIED]: number;
  zeroInbound: boolean;
};

/** The month label, plus a marker for a month with no inbound material
 * at all. A processor that certifies a fixed tonnage every month —
 * including months when nothing was weighed in — is the single clearest
 * thing this chart can show, and it is invisible if those months look
 * like any other. Marked with a shape as well as a colour, so the cue
 * doesn't depend on colour vision. Recharts clones this element with
 * x/y/payload injected, hence the optional props. */
function MonthTick({
  x,
  y,
  payload,
  zeroMonths,
  colors,
}: {
  // Recharts types its injected tick props loosely (x/y can arrive as
  // strings), so these are widened and coerced rather than asserted.
  x?: number | string;
  y?: number | string;
  payload?: { value?: string | number };
  zeroMonths: Set<string>;
  colors: ChartColors;
}) {
  const label = String(payload?.value ?? "");
  const isZero = zeroMonths.has(label);
  return (
    <g transform={`translate(${Number(x ?? 0)},${Number(y ?? 0)})`}>
      <text
        x={0}
        y={0}
        dy={12}
        textAnchor="middle"
        fontSize={12}
        fill={isZero ? colors.zeroMarker : colors.axisText}
      >
        {label}
      </text>
      {isZero ? <circle cx={0} cy={21} r={2.5} fill={colors.zeroMarker} /> : null}
    </g>
  );
}

/** Replaces Recharts' default tooltip because the certified figure is
 * drawn twice (bar and line share one dataKey), which the default
 * renders as two identical rows. Reads the point itself rather than the
 * series list, so each month shows exactly two numbers. */
function FlowTooltip({
  active,
  payload,
  colors,
}: {
  active?: boolean;
  payload?: { payload: FlowPoint }[];
  colors: ChartColors;
}) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return (
    <div className="card px-3 py-2 text-xs">
      <div className="font-medium text-ink">{point.month}</div>
      <div className="mt-1 flex items-center justify-between gap-4">
        <span style={{ color: colors.certifiedLine }}>Certified</span>
        <span className="tabular-nums text-ink">{formatTonnes(point[CERTIFIED])}</span>
      </div>
      <div className="flex items-center justify-between gap-4">
        <span style={{ color: colors.verifiedLine }}>Verified inbound</span>
        <span className="tabular-nums text-ink">{formatTonnes(point[VERIFIED])}</span>
      </div>
      {point.zeroInbound ? (
        <div className="mt-1 text-ink-muted">No material weighed in this month.</div>
      ) : null}
    </div>
  );
}

function KeySwatch({ children }: { children: React.ReactNode }) {
  return (
    <svg width={28} height={12} aria-hidden="true" className="mt-0.5 shrink-0">
      {children}
    </svg>
  );
}

export function MonthlyFlowChart({ rows }: { rows: MonthlyFlowRow[] }) {
  const colors = useChartColors();
  const data: FlowPoint[] = rows.map((row) => ({
    month: formatMonth(row.month),
    [CERTIFIED]: row.certified_t,
    [VERIFIED]: row.verified_inbound_t,
    zeroInbound: row.verified_inbound_t === 0,
  }));
  const zeroMonths = new Set(data.filter((d) => d.zeroInbound).map((d) => d.month));

  return (
    <div className="flex flex-col gap-3">
      <div className="h-126 w-full pt-9">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={colors.grid} vertical={false} />
            <XAxis
              dataKey="month"
              height={34}
              interval={0}
              tick={(props) => <MonthTick {...props} zeroMonths={zeroMonths} colors={colors} />}
            />
            <YAxis
              tick={{ fontSize: 12, fill: colors.axisText }}
              tickFormatter={(value: number) => value.toLocaleString("en-IN")}
              width={64}
            />
            <Tooltip content={<FlowTooltip colors={colors} />} />
            <Bar dataKey={CERTIFIED} fill={colors.certifiedBar} radius={[2, 2, 0, 0]} />
            {/* Same dataKey as the bar, drawn straight (never monotone) so
                it passes exactly through every bar top rather than
                curving between them — the point is that the two series
                are directly comparable as lines. */}
            <Line
              type="linear"
              dataKey={CERTIFIED}
              stroke={colors.certifiedLine}
              strokeWidth={2}
              strokeDasharray="5 4"
              dot={{ r: 3, fill: colors.certifiedLine, strokeWidth: 0 }}
              isAnimationActive={false}
            />
            <Line
              type="linear"
              dataKey={VERIFIED}
              stroke={colors.verifiedLine}
              strokeWidth={2}
              dot={{ r: 3, fill: colors.verifiedLine, strokeWidth: 0 }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <dl className="flex flex-col gap-2 text-xs text-ink-muted sm:flex-row sm:flex-wrap sm:gap-x-6">
        <div className="flex items-start gap-2">
          <KeySwatch>
            <line
              x1={0}
              y1={6}
              x2={28}
              y2={6}
              stroke={colors.certifiedLine}
              strokeWidth={2}
              strokeDasharray="5 4"
            />
          </KeySwatch>
          <div>
            <dt className="inline font-medium text-ink">Certified</dt>{" "}
            <dd className="inline">
              tonnes of recycling claimed for that month. The bars show the same figure.
            </dd>
          </div>
        </div>
        <div className="flex items-start gap-2">
          <KeySwatch>
            <line x1={0} y1={6} x2={28} y2={6} stroke={colors.verifiedLine} strokeWidth={2} />
          </KeySwatch>
          <div>
            <dt className="inline font-medium text-ink">Verified inbound</dt>{" "}
            <dd className="inline">
              tonnes weighed in and matched to an invoice and e-way bill.
            </dd>
          </div>
        </div>
        <div className="flex items-start gap-2">
          <KeySwatch>
            <circle cx={14} cy={6} r={2.5} fill={colors.zeroMarker} />
          </KeySwatch>
          <div>
            <dt className="inline font-medium text-ink">Marked month</dt>{" "}
            <dd className="inline">no material was weighed in at all.</dd>
          </div>
        </div>
      </dl>

      <p className="max-w-[80ch] text-pretty text-xs leading-relaxed text-ink-muted">
        Where the certified line sits above the verified line, the gap is tonnage this report could
        not verify from the processor&rsquo;s own documents. A certified line that stays flat while
        the verified line moves means the same tonnage was certified every month regardless of how
        much material actually arrived.
      </p>
    </div>
  );
}
