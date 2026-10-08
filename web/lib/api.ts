import type { components } from "@/lib/api-types";

export type Health = {
  status: string;
  model: string;
  region: string;
  consistency_ok: boolean | null;
};

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
export type AlertsResponse = components["schemas"]["AlertsResponse"];
export type FindingOut = components["schemas"]["FindingOut"];
export type CheckResultOut = components["schemas"]["CheckResultOut"];
export type StageAssessment = components["schemas"]["StageAssessment"];

export class ApiError extends Error {
  status: number;
  constructor(path: string, status: number) {
    super(`API ${path} returned ${status}`);
    this.status = status;
  }
}

function baseUrl(): string {
  return process.env.API_BASE_URL ?? "http://localhost:8080";
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${baseUrl()}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new ApiError(path, response.status);
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

export function getBrands(): Promise<BrandsResponse> {
  return getJson<BrandsResponse>("/brands");
}

export function getPortfolio(brandId: string): Promise<PortfolioResponse> {
  return getJson<PortfolioResponse>(`/portfolio/${encodeURIComponent(brandId)}`);
}

export function getEvaluation(): Promise<EvaluationResponse> {
  return getJson<EvaluationResponse>("/evaluation");
}

export function getAlerts(): Promise<AlertsResponse> {
  return getJson<AlertsResponse>("/alerts");
}
