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
import type { AccuracyComparison, BasisSeries } from "@/lib/evaluation";
import { useChartColors, type ChartColors } from "@/lib/useChartColors";

const RULE_CHECKS = "Rule Checks";
const AGENT_VALIDATION = "Agent Validation";

type BarPoint = {
  basis: string;
  [RULE_CHECKS]: number | null;
  [AGENT_VALIDATION]: number | null;
  ruleChecksLabel: string;
  agentValidationLabel: string;
};

/** Value labels are read from precomputed string fields rather than a
 * formatter, so each mark shows exactly the figure the table shows. */
function toPoints(series: BasisSeries[]): BarPoint[] {
  return series.map((basis) => {
    const ruleChecks = basis.stages.find((s) => s.stage === "checks_only");
    const agentValidation = basis.stages.find((s) => s.stage === "full");
    return {
      basis: basis.basisLabel,
      [RULE_CHECKS]: ruleChecks?.ratio ?? null,
      [AGENT_VALIDATION]: agentValidation?.ratio ?? null,
      ruleChecksLabel: ruleChecks?.display ?? "",
      agentValidationLabel: agentValidation?.display ?? "",
    };
  });
}

function ComparisonTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { payload: BarPoint }[];
}) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return (
    <div className="card px-3 py-2 text-xs">
      <div className="font-medium text-ink">{point.basis}</div>
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

function Panel({
  points,
  colors,
  domain,
}: {
  points: BarPoint[];
  colors: ChartColors;
  domain: [number, number] | undefined;
}) {
  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={points} margin={{ top: 20, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke={colors.grid} vertical={false} />
          <XAxis
            dataKey="basis"
            height={34}
            interval={0}
            tick={{ fontSize: 12, fill: colors.axisText }}
          />
          <YAxis
            domain={domain}
            tick={{ fontSize: 12, fill: colors.axisText }}
            tickFormatter={(value: number) => `${(value * 100).toFixed(domain ? 0 : 1)}%`}
            width={56}
          />
          <Tooltip content={<ComparisonTooltip />} />
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
              fontSize={11}
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
              fontSize={11}
              fill={colors.axisText}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Swatches take their colour from the CSS tokens, not from the hook:
 * these elements are server-rendered, and the hook cannot know the theme
 * until next-themes mounts on the client. */
function Key() {
  return (
    <dl className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-xs text-ink-muted">
      {[
        { label: RULE_CHECKS, swatch: "bg-chart-baseline", hint: "Deterministic Checks Alone" },
        { label: AGENT_VALIDATION, swatch: "bg-chart-series", hint: "After the Agents Reviewed Them" },
      ].map((entry) => (
        <div key={entry.label} className="flex items-center gap-1.5">
          <span aria-hidden="true" className={`size-2.5 shrink-0 rounded-sm ${entry.swatch}`} />
          <dt className="inline font-medium text-ink">{entry.label}</dt>
          <dd className="inline">{entry.hint}</dd>
        </div>
      ))}
    </dl>
  );
}

function figuresFor(series: BasisSeries[], unit: string) {
  return series.flatMap((basis) =>
    basis.stages.map((stage) => (
      <FiguresRow
        key={`${basis.factsSource}-${stage.stage}`}
        header={`${basis.basisLabel} — ${stage.stageLabel}`}
        values={[stage.display, `${stage.numerator}/${stage.denominator} ${unit}`]}
      />
    ))
  );
}

export function AccuracyComparisonChart({ comparison }: { comparison: AccuracyComparison }) {
  const colors = useChartColors();

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      {comparison.bandAccuracy.length > 0 ? (
        <ChartPanel
          title="Risk-band accuracy by stage"
          caption="Share of processors placed in the risk band the ground truth records, before and after agent validation, on each set of facts. Higher is better."
          figures={
            <FiguresTable
              caption="Risk-band accuracy by facts source and stage."
              headers={["Measurement", "Accuracy", "Processors matched"]}
            >
              {figuresFor(comparison.bandAccuracy, "processors")}
            </FiguresTable>
          }
        >
          <Panel points={toPoints(comparison.bandAccuracy)} colors={colors} domain={[0, 1]} />
          <Key />
        </ChartPanel>
      ) : null}

      {comparison.tonnageError.length > 0 ? (
        <ChartPanel
          title="Tonnage error by stage"
          caption="Mean error in assessed verifiable tonnes, as a share of the true figure, before and after agent validation. Lower is better; zero means every processor's tonnage matched exactly."
          figures={
            <FiguresTable
              caption="Tonnage error by facts source and stage."
              headers={["Measurement", "Error", "Stored as"]}
            >
              {figuresFor(comparison.tonnageError, "millionths")}
            </FiguresTable>
          }
        >
          <Panel points={toPoints(comparison.tonnageError)} colors={colors} domain={undefined} />
          <Key />
        </ChartPanel>
      ) : null}
    </div>
  );
}
