const tonnesFormatter = new Intl.NumberFormat("en-IN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const m2Formatter = new Intl.NumberFormat("en-IN", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

/** The number half of formatTonnes, with no " t" suffix — for contexts
 * (T13.5b plan, Part 1/5: MetricTile, CountUp) that style the unit as its
 * own separate element rather than concatenating it into one string. */
export function formatTonnesValue(value: number): string {
  return tonnesFormatter.format(value);
}

export function formatTonnes(value: number): string {
  return `${formatTonnesValue(value)} t`;
}

export function formatSignedTonnes(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${tonnesFormatter.format(value)} t`;
}

export function formatPercent(ratio: number): string {
  return `${(ratio * 100).toFixed(1)}%`;
}

/** The percentage rule for /evaluation, and the only one used there.
 * Mirrors api/app/eval/evaluate.py's format_accuracy_pct — the rule GET
 * /stats already applies to the landing page's field-read figure: two
 * decimal places, TRUNCATED rather than rounded, so a not-quite-perfect
 * ratio can never print as "100%" (5,430/5,431 is 99.98%, not 100%).
 * Exact equality is the only path to "100%". Trailing zeros are then
 * trimmed, so 0.7 reads "70%" and 0.019545 reads "1.95%". Kept separate
 * from formatPercent, which lib/checks.ts uses for check ratios at one
 * decimal place. */
export function formatPercentPrecise(ratio: number): string {
  const pct = ratio === 1 ? 100 : Math.floor(ratio * 10_000) / 100;
  return `${pct.toFixed(2).replace(/0+$/, "").replace(/\.$/, "")}%`;
}

export function formatKwhPerT(value: number): string {
  return `${tonnesFormatter.format(value)} kWh/t`;
}

export function formatM2(value: number): string {
  return `${m2Formatter.format(value)} m²`;
}

export function formatMonth(month: string): string {
  const [year, m] = month.split("-").map(Number);
  if (!year || !m) return month;
  return new Date(Date.UTC(year, m - 1, 1)).toLocaleDateString("en-US", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** Clock time in IST (T16b). Stage timestamps come back as UTC — the API
 * stores every document time as UTC and the project displays IST — so the
 * zone is pinned rather than left to the viewer's locale, which would
 * otherwise show a demo run's stages in whatever zone the browser is set
 * to. Time only, no date: these are stages of a single run minutes long,
 * where a date would be noise. */
export function formatIstTime(iso: string): string | null {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return null;
  return `${parsed.toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "Asia/Kolkata",
  })} IST`;
}

export type RiskBand = "Low" | "Medium" | "High" | string;

export function riskBandTone(band: RiskBand): "low" | "medium" | "high" | "unknown" {
  switch (band) {
    case "Low":
      return "low";
    case "Medium":
      return "medium";
    case "High":
      return "high";
    default:
      return "unknown";
  }
}
