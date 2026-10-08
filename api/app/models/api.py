"""Response models for every GET endpoint in docs/ARCHITECTURE.md §7
(T11). Pure data, no I/O — app/store/cache.py builds these from BigQuery
rows; app/main.py's routes just call cache and return the result.
"""

from typing import Any, Literal

from pydantic import BaseModel


class Meta(BaseModel):
    seed: int
    facts_source: str


# ---------- checks ----------


class CheckResultOut(BaseModel):
    check_id: str
    status: str
    severity: str
    measured: float | None
    threshold: float | None
    affected_tonnes: float | None
    evidence_ids: list[str]
    explanation: str
    source: str  # app/checks/params.py's CHECK_SOURCE_LABELS


class StageAssessment(BaseModel):
    certified_t: float
    verified_inbound_t: float
    capacity_limit_t: float
    verifiable_t: float
    unverifiable_t: float
    risk_band: str


# ---------- agent findings ----------

FindingClassification = Literal[
    "deductible", "systemic", "no_own_evidence", "concurs_with_check", "review_flag", "withdrawn"
]


class VerdictOut(BaseModel):
    by: Literal["critic"] = "critic"
    verdict: Literal["upheld", "disputed"]
    reason: str


class RevisionOut(BaseModel):
    by: Literal["hypothesis"]
    decision: str  # "accept"/"reject" (Critic-raised) or "maintain"/"withdraw" (Hypothesis-origin)
    explanation: str


class FindingOut(BaseModel):
    finding_type: str
    classification: FindingClassification
    effect: str
    cited_shipment_ids: list[str]
    evidence_ids: list[str]
    explanation: str
    origin: Literal["hypothesis", "critic"]
    proposed_by: Literal["hypothesis", "critic"]  # == origin, explicit name for the UI
    verdict: VerdictOut | None
    disputed_by: RevisionOut | None


# ---------- processors ----------


class ProcessorSummary(BaseModel):
    processor_id: str
    name: str
    type: str
    checks_only: StageAssessment
    full: StageAssessment | None
    agent_status: str | None


class ProcessorListResponse(BaseModel):
    meta: Meta
    processors: list[ProcessorSummary]


class ProcessorProfile(BaseModel):
    processor_id: str
    name: str
    type: str
    capacity_t_per_year: float
    permitted_categories: list[str]
    consent_no: str
    consent_valid_from: str
    consent_valid_to: str
    registration_no: str
    gstin: str
    address: str
    lat: float  # rounded to 2dp at the API layer — project rule §9
    lon: float


class MonthlyFlowRow(BaseModel):
    month: str
    certified_t: float
    verified_inbound_t: float


class ProcessorDetailResponse(BaseModel):
    meta: Meta
    profile: ProcessorProfile
    monthly_flow: list[MonthlyFlowRow]
    check_results: list[CheckResultOut]
    checks_only: StageAssessment
    full: StageAssessment | None
    agent_status: str | None
    findings: list[FindingOut]


# ---------- reasoning trail ----------


class ReasoningStepOut(BaseModel):
    """step_type="critic_tool" is a single merged step for what used to be
    a critic_tool_call + critic_tool_result pair (and, for read_document,
    a trailing attachment row too) — tool_name/tool_args/result/
    result_summary are populated only for this step type; output is
    populated for every other step type (hypothesis/critic_final/
    revision/critic_model_turn/tool_cap_reached/score). result is the
    tool's own parsed return value — a list or dict for every real tool,
    occasionally a bare string for the "already returned in call N"
    dedup-hit message, which isn't valid JSON to parse back into an
    object (docs/BUILD_PLAN.md A2)."""

    step_index: int
    step_type: str
    tool_name: str | None
    tool_args: dict | None
    output: dict | None
    result: Any | None
    result_summary: str | None
    latency_ms: float | None
    tokens: dict | None
    dedup_hit: bool


class ReasoningResponse(BaseModel):
    meta: Meta
    processor_id: str
    agent_status: str | None
    tool_cap_reached: bool
    steps: list[ReasoningStepOut]
    findings: list[FindingOut]


# ---------- site ----------


class SiteResponse(BaseModel):
    meta: Meta
    processor_id: str
    status: str
    severity: str
    measured: float | None
    threshold: float | None
    building_count: int
    total_footprint_m2: float
    thumb_bbox: list[float]  # [w, s, e, n], rounded to 2dp
    thumb_crs: str
    explanation: str
    sentinel_attribution: str
    open_buildings_attribution: str
    disclaimer: str = "Locations are illustrative and rounded; this is synthetic demo data."


# ---------- documents ----------


class DocumentListItem(BaseModel):
    doc_id: str
    doc_type: str
    lang: str
    extraction_status: Literal["ok", "failed", "not_extracted"]


class DocumentsResponse(BaseModel):
    meta: Meta
    processor_id: str
    documents: list[DocumentListItem]


class ExtractedFieldOut(BaseModel):
    field_name: str
    printed_value: str
    confidence: float | None
    page: int | None


class DocumentFactsResponse(BaseModel):
    meta: Meta
    doc_id: str
    extraction_status: Literal["ok", "failed", "not_extracted"]
    error_message: str | None
    fields: list[ExtractedFieldOut]


# ---------- brands ----------


class BrandListItem(BaseModel):
    brand_id: str
    name: str


class BrandsResponse(BaseModel):
    meta: Meta
    brands: list[BrandListItem]


# ---------- portfolio ----------


class PortfolioCertificateRow(BaseModel):
    certificate_id: str
    processor_id: str
    category: str
    quantity_t: float
    period_month: str
    processor_risk_band: str | None


class PortfolioResponse(BaseModel):
    meta: Meta
    brand_id: str
    brand_name: str
    total_certified_t: float
    # Each certificate's quantity_t apportioned by its own processor's
    # verifiable_t / certified_t ratio and summed — a derived apportionment,
    # not a traced per-certificate figure (no scoring is done below the
    # processor/FY-to-date level anywhere upstream). docs/ARCHITECTURE.md
    # §7 states this explicitly so T12 doesn't present it as more precise
    # than it is.
    total_verifiable_t: float
    certificates: list[PortfolioCertificateRow]


# ---------- evaluation / alerts (explicit empty states until T14/T13) ----------


class EvaluationResponse(BaseModel):
    meta: Meta
    available: bool = False
    message: str = "Evaluation metrics are not yet available — see docs/BUILD_PLAN.md T14."


class AlertsResponse(BaseModel):
    meta: Meta
    alerts: list[dict] = []
