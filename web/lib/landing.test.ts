import { describe, expect, it, vi } from "vitest";
import { getLandingFigures } from "./landing";
import * as api from "./api";

describe("getLandingFigures", () => {
  it("maps a successful /stats response into LandingFigures", async () => {
    vi.spyOn(api, "getStats").mockResolvedValue({
      meta: { seed: 42, facts_source: "extracted" },
      processors_count: 10,
      documents_read: 714,
      fields_read: 5523,
      certified_t_total: 51234.56,
      unverifiable_t_total: 9876.54,
      as_of: "2026-03",
      fy_label: "FY 2025-26 to date",
      field_read_accuracy_pct: "99.96%",
      field_read_accuracy_value: 99.96,
      field_read_correct: 5521,
      field_read_total: 5523,
      field_read_dataset_label: "dev-seed42",
    });

    const figures = await getLandingFigures();

    expect(figures).toEqual({
      processorsVerified: 10,
      certifiedTonnes: 51234.56,
      unverifiableTonnes: 9876.54,
      documentsRead: 714,
      fyLabel: "FY 2025-26 to date",
      fieldReadAccuracyPct: "99.96%",
      fieldReadAccuracyValue: 99.96,
    });
  });

  it("returns null when /stats fails, so the landing page can hide the figures gracefully", async () => {
    vi.spyOn(api, "getStats").mockResolvedValue(null);

    const figures = await getLandingFigures();

    expect(figures).toBeNull();
  });
});
