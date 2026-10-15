"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartPanel, FiguresRow, FiguresTable } from "@/components/evaluation/ChartPanel";
import { formatErrorTonnes, type ProcessorErrors } from "@/lib/evaluation";

/** Recharts wraps a label wider than its bar onto a second line, which
 * splits "0.000 t" across two rows. A non-breaking space removes the only
 * break opportunity, so the label stays on one line and the unit stays
 * attached to its number. */
function barLabel(kg: number): string {
  return formatErrorTonnes(kg).replace(" ", "\u00a0");
}
import { useChartColors } from "@/lib/useChartColors";

const RULE_CHECKS = "Rule Checks";
const AGENT_VALIDATION = "Agent Validation";

/** The chart plots the ground-truth pair: it is the basis the headline
 * tonnage-error figure is quoted on, so the two agree. Both fact sources
 * are in the figures table. */
const PLOTTED_FACTS_SOURCE = "truth";

type ErrorPoint = {
  processorId: string;
  [RULE_CHECKS]: number | null;
  [AGENT_VALIDATION]: number | null;
  ruleChecksLabel: string;
  agentValidationLabel: string;
};

function ErrorTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: ErrorPoint }[];
}) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return (
    <div className="card px-3 py-2 text-xs">
      <div className="font-medium text-ink">{point.processorId}</div>
      <div className="mt-1 flex items-center justify-between gap-4">
        <span className="flex items-center gap-1.5 text-ink-muted">
          <span aria-hidden="true" className="size-2 shrink-0 rounded-sm bg-chart-baseline" />
          {RULE_CHECKS}
        </span>
        <span className="tabular-nums text-ink">{point.ruleChecksLabel || "—"}</span>
      </div>
      <div className="flex items-center justify-between gap-4">
        <span className="flex items-center gap-1.5 text-ink-muted">
          <span aria-hidden="true" className="size-2 shrink-0 rounded-sm bg-chart-series" />
          {AGENT_VALIDATION}
        </span>
        <span className="tabular-nums text-ink">{point.agentValidationLabel || "—"}</span>
      </div>
    </div>
  );
}

export function ProcessorErrorChart({ errors }: { errors: ProcessorErrors }) {
  const colors = useChartColors();

  const ruleChecksKey = `checks_only_${PLOTTED_FACTS_SOURCE}`;
  const agentKey = `full_${PLOTTED_FACTS_SOURCE}`;
  const plotted = errors.columns.some((column) => column.key === ruleChecksKey || column.key === agentKey);
  if (!plotted) return null;

  const points: ErrorPoint[] = errors.processorIds.map((processorId) => {
    const ruleChecksKg = errors.kg[processorId]?.[ruleChecksKey];
    const agentKg = errors.kg[processorId]?.[agentKey];
    return {
      processorId,
      [RULE_CHECKS]: ruleChecksKg === undefined ? null : ruleChecksKg / 1000,
      [AGENT_VALIDATION]: agentKg === undefined ? null : agentKg / 1000,
      ruleChecksLabel: ruleChecksKg === undefined ? "" : barLabel(ruleChecksKg),
      agentValidationLabel: agentKg === undefined ? "" : barLabel(agentKg),
    };
  });

  return (
    <ChartPanel
      title="Tonnage error by processor"
      caption="How far each processor's assessed verifiable tonnes sat from the ground truth, on ground-truth facts. A bar flattened to the axis and labelled 0.000 t means that processor's tonnage was exact. The figures table also carries the extracted-facts measurements."
      figures={
        <FiguresTable
          caption="Absolute verifiable-tonnes error per processor, for every stage and facts source."
          headers={["Processor", ...errors.columns.map((column) => column.label)]}
        >
          {errors.processorIds.map((processorId) => (
            <FiguresRow
              key={processorId}
              header={processorId}
              values={errors.columns.map((column) => {
                const kg = errors.kg[processorId]?.[column.key];
                return kg === undefined ? null : formatErrorTonnes(kg);
              })}
            />
          ))}
        </FiguresTable>
      }
    >
      <div className="overflow-x-auto" role="region" aria-label="Tonnage error by processor, chart" tabIndex={0}>
        <div className="h-72 w-full min-w-[34rem]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={points} margin={{ top: 20, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={colors.grid} vertical={false} />
              <XAxis
                dataKey="processorId"
                height={34}
                interval={0}
                tick={{ fontSize: 11, fill: colors.axisText }}
              />
              <YAxis
                tick={{ fontSize: 12, fill: colors.axisText }}
                tickFormatter={(value: number) => `${value.toFixed(1)} t`}
                width={64}
              />
              <Tooltip content={<ErrorTooltip />} />
              <Bar
                dataKey={RULE_CHECKS}
                fill={colors.seriesBaseline}
                radius={[2, 2, 0, 0]}
                // A zero-valued series would otherwise draw nothing at all,
                // leaving the legend promising a series the reader cannot
                // find — and zero IS the result worth seeing here. A 2px
                // stub keeps the slot visible; the value label above it
                // states the figure, so the stub can't be read as a small
                // nonzero value.
                minPointSize={2}
                isAnimationActive={false}
              >
                <LabelList
                  dataKey="ruleChecksLabel"
                  position="top"
                  fontSize={10}
                  fill={colors.axisText}
                />
              </Bar>
              <Bar
                dataKey={AGENT_VALIDATION}
                fill={colors.series}
                radius={[2, 2, 0, 0]}
                // A zero-valued series would otherwise draw nothing at all,
                // leaving the legend promising a series the reader cannot
                // find — and zero IS the result worth seeing here. A 2px
                // stub keeps the slot visible; the value label above it
                // states the figure, so the stub can't be read as a small
                // nonzero value.
                minPointSize={2}
                isAnimationActive={false}
              >
                <LabelList
                  dataKey="agentValidationLabel"
                  position="top"
                  fontSize={10}
                  fill={colors.axisText}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <dl className="mt-2 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-xs text-ink-muted">
        {[
          { label: RULE_CHECKS, swatch: "bg-chart-baseline" },
          { label: AGENT_VALIDATION, swatch: "bg-chart-series" },
        ].map((entry) => (
          <div key={entry.label} className="flex items-center gap-1.5">
            <span aria-hidden="true" className={`size-2.5 shrink-0 rounded-sm ${entry.swatch}`} />
            <dt className="inline font-medium text-ink">{entry.label}</dt>
            <dd className="inline">on Ground-Truth Facts</dd>
          </div>
        ))}
      </dl>
    </ChartPanel>
  );
}
