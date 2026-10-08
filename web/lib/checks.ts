import { formatKwhPerT, formatPercent, formatTonnes } from "@/lib/format";

// Units per check, from api/app/checks/params.py's own threshold comments
// (CHECK_SOURCE_LABELS/the constants it documents) — the API returns raw
// measured/threshold floats with no unit field, so this is a small,
// source-grounded lookup rather than a guess.
const RATIO_CHECKS = new Set(["C2a", "C2b", "C4", "AGENT_SYSTEMIC_FINDING"]);
const TONNES_CHECKS = new Set(["C1"]);
const SPEED_CHECKS = new Set(["C3a"]);
const KWH_CHECKS = new Set(["C7"]);
const DENSITY_CHECKS = new Set(["C8"]);

export function formatCheckValue(checkId: string, value: number | null): string {
  if (value === null) return "—";
  if (RATIO_CHECKS.has(checkId)) return formatPercent(value);
  if (TONNES_CHECKS.has(checkId)) return formatTonnes(value);
  if (SPEED_CHECKS.has(checkId)) return `${value.toFixed(1)} km/h`;
  if (KWH_CHECKS.has(checkId)) return formatKwhPerT(value);
  if (DENSITY_CHECKS.has(checkId)) return `${value.toFixed(2)} t/m²`;
  return value.toFixed(2);
}

export const STATUS_LABEL: Record<string, string> = {
  pass: "Pass",
  fail: "Fail",
  warn: "Warn",
  not_evaluable: "Not evaluable",
};

export const STATUS_TONE: Record<string, string> = {
  pass: "text-risk-low",
  fail: "text-risk-high",
  warn: "text-risk-medium",
  not_evaluable: "text-slate-500",
};
