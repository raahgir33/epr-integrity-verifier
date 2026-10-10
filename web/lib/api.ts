import type { components } from "@/lib/api-types";

export type Health = {
  status: string;
};

export type ProcessorProfile = components["schemas"]["ProcessorProfile"];
export type ProcessorSummary = components["schemas"]["ProcessorSummary"];
export type ProcessorListResponse = components["schemas"]["ProcessorListResponse"];
export type ProcessorDetailResponse = components["schemas"]["ProcessorDetailResponse"];
export type DocumentListItem = components["schemas"]["DocumentListItem"];
export type DocumentsResponse = components["schemas"]["DocumentsResponse"];
export type DocumentFactsResponse = components["schemas"]["DocumentFactsResponse"];
export type MonthlyFlowRow = components["schemas"]["MonthlyFlowRow"];
export type ReasoningResponse = components["schemas"]["ReasoningResponse"];
export type ReasoningStepOut = components["schemas"]["ReasoningStepOut"];
export type SiteResponse = components["schemas"]["SiteResponse"];
export type BrandsResponse = components["schemas"]["BrandsResponse"];
export type PortfolioResponse = components["schemas"]["PortfolioResponse"];
export type EvaluationResponse = components["schemas"]["EvaluationResponse"];
export type EvalMetricRow = components["schemas"]["EvalMetricRow"];
export type AlertsResponse = components["schemas"]["AlertsResponse"];
export type AlertOut = components["schemas"]["AlertOut"];
export type DemoBatchOut = components["schemas"]["DemoBatchOut"];
export type DemoBatchesResponse = components["schemas"]["DemoBatchesResponse"];
export type DemoCertificateBatchResponse = components["schemas"]["DemoCertificateBatchResponse"];
export type RunStatusOut = components["schemas"]["RunStatusOut"];
export type FindingOut = components["schemas"]["FindingOut"];
export type CheckResultOut = components["schemas"]["CheckResultOut"];
export type StageAssessment = components["schemas"]["StageAssessment"];
export type MemoResponse = components["schemas"]["MemoResponse"];
export type StatsResponse = components["schemas"]["StatsResponse"];

export class ApiError extends Error {
  status: number;
  /** The API's own error message, when the error body was JSON shaped
   * {"error": "...", "request_id": "..."} (T13.8's uniform error envelope)
   * — T13's abuse-gate 429s (cooldown, daily cap, already running) carry a
   * user-facing message here. */
  detail?: string;
  constructor(path: string, status: number, detail?: string) {
    super(detail ?? `API ${path} returned ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

function baseUrl(): string {
  return process.env.API_BASE_URL ?? "http://localhost:8080";
}

/** T13.8: a network-level failure (API down, DNS, connection refused)
 * throws a raw `TypeError` from `fetch` itself, not an `ApiError` — wrap
 * it into a plain, clearly-labelled Error instead, so server logs read
 * "API unreachable: <path>" rather than an undifferentiated TypeError.
 * (Next.js redacts a Server Component error's message from the client in
 * production either way — see app/error.tsx's ErrorState — so this is
 * for log clarity, not for a client-visible distinction.) */
async function fetchOrThrow(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(`${baseUrl()}${path}`, init);
  } catch (cause) {
    // Next.js signals its own internal control flow (bailing out of
    // static generation with DYNAMIC_SERVER_USAGE, redirects, etc.)
    // by throwing from inside fetch() itself and tagging the error with
    // a `digest` — those must propagate completely unwrapped, or the
    // framework can no longer recognize them (this broke `npm run build`
    // before this check was added: it turned a normal "render this route
    // dynamically" signal into a fatal prerender error).
    if (cause && typeof cause === "object" && "digest" in cause) {
      throw cause;
    }
    throw new Error(`API unreachable: ${path}`, { cause });
  }
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetchOrThrow(path, { cache: "no-store" });
  if (!response.ok) {
    throw new ApiError(path, response.status);
  }
  return response.json();
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetchOrThrow(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!response.ok) {
    let detail: string | undefined;
    try {
      const data: unknown = await response.json();
      if (data && typeof data === "object" && "error" in data && typeof data.error === "string") {
        detail = data.error;
      }
    } catch {
      // non-JSON error body — detail stays undefined, status is still reported
    }
    throw new ApiError(path, response.status, detail);
  }
  return response.json();
}

export function getHealth(): Promise<Health> {
  return getJson<Health>("/health");
}

export function getProcessors(): Promise<ProcessorListResponse> {
  return getJson<ProcessorListResponse>("/processors");
}

export function getProcessor(id: string): Promise<ProcessorDetailResponse> {
  return getJson<ProcessorDetailResponse>(`/processors/${encodeURIComponent(id)}`);
}

export function getProcessorDocuments(id: string): Promise<DocumentsResponse> {
  return getJson<DocumentsResponse>(`/processors/${encodeURIComponent(id)}/documents`);
}

export function getDocumentFacts(docId: string): Promise<DocumentFactsResponse> {
  return getJson<DocumentFactsResponse>(`/documents/${encodeURIComponent(docId)}/facts`);
}

export function getProcessorReasoning(id: string): Promise<ReasoningResponse> {
  return getJson<ReasoningResponse>(`/processors/${encodeURIComponent(id)}/reasoning`);
}

export function getProcessorSite(id: string): Promise<SiteResponse> {
  return getJson<SiteResponse>(`/processors/${encodeURIComponent(id)}/site`);
}

/** Returns null (never throws) on a 404 — a processor with no memo/
 * statement yet (precompute pipeline hasn't reached --stage memo) is a
 * normal, expected state, not an error. Other failures still propagate,
 * same as every other fetch here (surfaced via app/error.tsx). */
export async function getProcessorMemo(id: string, lang: "en" | "hi"): Promise<MemoResponse | null> {
  try {
    return await getJson<MemoResponse>(`/processors/${encodeURIComponent(id)}/memo?lang=${lang}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export function getBrands(): Promise<BrandsResponse> {
  return getJson<BrandsResponse>("/brands");
}

export function getPortfolio(brandId: string): Promise<PortfolioResponse> {
  return getJson<PortfolioResponse>(`/portfolio/${encodeURIComponent(brandId)}`);
}

export function getEvaluation(): Promise<EvaluationResponse> {
  return getJson<EvaluationResponse>("/evaluation");
}

/** Returns null (never throws) on ANY failure — unlike every other getter
 * here, which propagates into app/error.tsx. T13.6's hero figures and
 * proof strip read /stats for numbers that used to be computed client-
 * side with a safe fallback (an empty metrics row); the brief is explicit
 * that a /stats outage must hide those labels gracefully, not break the
 * landing page. */
export async function getStats(): Promise<StatsResponse | null> {
  try {
    return await getJson<StatsResponse>("/stats");
  } catch {
    return null;
  }
}

export function getAlerts(): Promise<AlertsResponse> {
  return getJson<AlertsResponse>("/alerts");
}

export function getDemoBatches(): Promise<DemoBatchesResponse> {
  return getJson<DemoBatchesResponse>("/demo-batches");
}

export function postDemoBatch(batchId: string): Promise<DemoCertificateBatchResponse> {
  return postJson<DemoCertificateBatchResponse>("/demo/certificate-batch", { batch_id: batchId });
}

export function getRun(runId: string): Promise<RunStatusOut> {
  return getJson<RunStatusOut>(`/runs/${encodeURIComponent(runId)}`);
}
