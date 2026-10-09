import {
  getDocumentFacts,
  getProcessorDocuments,
  getProcessorMemo,
  type CheckResultOut,
  type DocumentFactsResponse,
  type DocumentListItem,
  type FindingOut,
  type MemoResponse,
  type ProcessorDetailResponse,
  type ProcessorSummary,
} from "@/lib/api";

/** A document id containing "DEMO" was added by T13's live certificate-
 * batch event path, not the committed base dataset (confirmed by the
 * naming convention in data/synthetic/seed-42/demo_extra/) — those
 * documents appear and disappear with demo runs and resets (Amendment B,
 * T13.5 plan), so the landing page's "real example" picks must exclude
 * them to stay stable regardless of whether a live run has happened. */
function isBaseDatasetDoc(doc: DocumentListItem): boolean {
  return !doc.doc_id.toUpperCase().includes("DEMO");
}

export type LandingFigures = {
  processorsVerified: number;
  certifiedTonnes: number;
  unverifiableTonnes: number;
  documentsRead: number;
};

/** Amendment A (T13.5 plan): certifiedTonnes sums checks_only.certified_t
 * (identical across stages); unverifiableTonnes prefers each processor's
 * full stage, falling back to checks_only — the same (full ?? checks_only)
 * pattern used on / (today's Overview totals), /processors/[id] and
 * ProcessorsTable, so this landing page never shows a different number
 * for the same underlying figure. documentsRead is a real count (one
 * GET /processors/{id}/documents per processor, ≤10 processors, same
 * cost class as the portfolio-preview section's own per-processor
 * fetches) — "document fields read" was an API gap flagged in the plan;
 * the developer chose "documents read" (a document count) instead. */
export async function getLandingFigures(processors: ProcessorSummary[]): Promise<LandingFigures> {
  const certifiedTonnes = processors.reduce((sum, p) => sum + p.checks_only.certified_t, 0);
  const unverifiableTonnes = processors.reduce(
    (sum, p) => sum + (p.full ?? p.checks_only).unverifiable_t,
    0,
  );
  const documentLists = await Promise.all(
    processors.map((p) => getProcessorDocuments(p.processor_id).catch(() => null)),
  );
  const documentsRead = documentLists.reduce((sum, d) => sum + (d?.documents.length ?? 0), 0);

  return {
    processorsVerified: processors.length,
    certifiedTonnes,
    unverifiableTonnes,
    documentsRead,
  };
}

export type CheckCatalogEntry = { checkId: string; severity: string; source: string };

/** "What we check" accordion data (T13.5 plan, Part 3 — approved with
 * two conditions): built from the UNION of check_ids across every
 * processor's check_results, not one processor's list, so a check
 * absent or not-applicable for any single processor still appears; a
 * check added to the pipeline later shows up automatically with its
 * real severity/source, no code change needed here. */
export function buildCheckCatalog(details: ProcessorDetailResponse[]): CheckCatalogEntry[] {
  const byId = new Map<string, CheckCatalogEntry>();
  for (const detail of details) {
    for (const check of detail.check_results) {
      if (!byId.has(check.check_id)) {
        byId.set(check.check_id, { checkId: check.check_id, severity: check.severity, source: check.source });
      }
    }
  }
  return [...byId.values()].sort((a, b) => a.checkId.localeCompare(b.checkId));
}

export type RealExamples = {
  hindiDoc: { processorId: string; doc: DocumentListItem; facts: DocumentFactsResponse } | null;
  failingCheck: { processorId: string; check: CheckResultOut } | null;
  finding: { processorId: string; finding: FindingOut } | null;
  memo: { processorId: string; memo: MemoResponse } | null;
};

/** How-it-works step examples (T13.5 plan, Part 3) — one real instance
 * per step, pulled from already-fetched processor detail/document data
 * wherever possible, base-dataset documents only (Amendment B). Each
 * pick is independent (different steps may come from different
 * processors) — the goal is one genuine example per step, not one
 * matching processor end to end. */
export async function pickRealExamples(
  processorIds: string[],
  details: ProcessorDetailResponse[],
): Promise<RealExamples> {
  let hindiDoc: RealExamples["hindiDoc"] = null;
  for (const processorId of processorIds) {
    const docs = await getProcessorDocuments(processorId).catch(() => null);
    const candidate = docs?.documents.find((d) => d.lang === "hi" && isBaseDatasetDoc(d));
    if (candidate) {
      const facts = await getDocumentFacts(candidate.doc_id).catch(() => null);
      if (facts && facts.fields.length > 0) {
        hindiDoc = { processorId, doc: candidate, facts };
        break;
      }
    }
  }

  let failingCheck: RealExamples["failingCheck"] = null;
  for (const detail of details) {
    const candidate = detail.check_results.find((c) => c.status === "fail" || c.status === "warn");
    if (candidate) {
      failingCheck = { processorId: detail.profile.processor_id, check: candidate };
      break;
    }
  }

  let finding: RealExamples["finding"] = null;
  for (const detail of details) {
    const candidate = detail.findings.find((f) => f.classification !== "withdrawn");
    if (candidate) {
      finding = { processorId: detail.profile.processor_id, finding: candidate };
      break;
    }
  }

  let memo: RealExamples["memo"] = null;
  for (const detail of details) {
    const processorId = detail.profile.processor_id;
    const candidate = await getProcessorMemo(processorId, "en").catch(() => null);
    if (candidate && candidate.doc_type === "clarification_memo") {
      memo = { processorId, memo: candidate };
      break;
    }
  }

  return { hindiDoc, failingCheck, finding, memo };
}

/** Portfolio-preview card data (T13.5 plan, Part 3, section 5). Amendment
 * F: a processor with zero unverifiable tonnes gets a positive headline
 * instead of an empty "no finding" line. */
export function topFindingHeadline(detail: ProcessorDetailResponse): string {
  const stage = detail.full ?? detail.checks_only;
  if (stage.unverifiable_t <= 0) return "Verified — no unverifiable tonnes";
  const displayed = detail.findings.find((f) => f.classification !== "withdrawn");
  return displayed ? displayed.finding_type : "Unverifiable tonnes flagged by deterministic checks";
}
