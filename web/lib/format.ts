const tonnesFormatter = new Intl.NumberFormat("en-IN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const m2Formatter = new Intl.NumberFormat("en-IN", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

export function formatTonnes(value: number): string {
  return `${tonnesFormatter.format(value)} t`;
}

export function formatSignedTonnes(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${tonnesFormatter.format(value)} t`;
}

export function formatPercent(ratio: number): string {
  return `${(ratio * 100).toFixed(1)}%`;
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
