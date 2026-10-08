"""FastAPI app and routes (docs/ARCHITECTURE.md §7). Every GET route reads
through app/store/cache.py, never BigQuery/GCS directly except for the two
file-streaming routes, which still validate against the cache first (no
arbitrary paths). Nothing in this module writes to BigQuery or GCS — the
live event path (POST /demo/certificate-batch, GET /runs/{run_id},
POST /events/certificate-batch) is T13's, not built here.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response

from app.config import settings
from app.geo import site as geo_site
from app.models.api import (
    AlertsResponse,
    DocumentFactsResponse,
    DocumentsResponse,
    EvaluationResponse,
    PortfolioResponse,
    ProcessorDetailResponse,
    ProcessorListResponse,
    ReasoningResponse,
    SiteResponse,
)
from app.store import cache, gcs


@asynccontextmanager
async def lifespan(app: FastAPI):
    cache.preload(settings.default_seed, settings.default_facts_source)
    yield


app = FastAPI(title="epr-api", lifespan=lifespan)


def _meta() -> dict:
    return {"seed": settings.default_seed, "facts_source": settings.default_facts_source}


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "model": settings.gemini_model,
        "region": settings.vertex_location,
    }


@app.get("/processors", response_model=ProcessorListResponse)
def list_processors() -> dict:
    seed, facts_source = settings.default_seed, settings.default_facts_source
    return {"meta": _meta(), "processors": cache.list_processors(seed, facts_source)}


@app.get("/processors/{processor_id}", response_model=ProcessorDetailResponse)
def get_processor(processor_id: str) -> dict:
    seed, facts_source = settings.default_seed, settings.default_facts_source
    profile = cache.get_processor_profile(seed, processor_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="processor not found")
    assessments = cache.get_processor_assessments(seed, facts_source, processor_id)
    if assessments is None or assessments["checks_only"] is None:
        # checks_only is the response model's one non-optional stage — a
        # processor missing it (no --stage checks run yet) isn't part of
        # the served dataset, same as a processor missing entirely.
        raise HTTPException(
            status_code=404, detail="processor has not been scored for this dataset"
        )
    return {
        "meta": _meta(),
        "profile": profile,
        "monthly_flow": cache.get_monthly_flow(seed, facts_source, processor_id),
        "check_results": cache.get_check_results(seed, facts_source, processor_id),
        "checks_only": assessments["checks_only"],
        "full": assessments["full"],
        "agent_status": assessments["agent_status"],
        "findings": cache.get_findings(seed, facts_source, processor_id),
    }


@app.get("/processors/{processor_id}/documents", response_model=DocumentsResponse)
def get_processor_documents(processor_id: str) -> dict:
    seed = settings.default_seed
    if cache.get_processor_profile(seed, processor_id) is None:
        raise HTTPException(status_code=404, detail="processor not found")
    return {
        "meta": _meta(),
        "processor_id": processor_id,
        "documents": cache.get_documents_for_processor(seed, processor_id),
    }


@app.get("/documents/{doc_id}/file")
def get_document_file(doc_id: str) -> Response:
    """doc_id is validated against the documents table for the configured
    seed before any GCS read (docs/BUILD_PLAN.md T11) — no arbitrary
    paths; the GCS blob path always comes from the row we looked up, never
    from the request."""
    doc = cache.get_document(settings.default_seed, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    data = gcs.download_bytes(gcs.get_client(), settings.dossier_bucket, doc["gcs_path"])
    return Response(
        content=data,
        media_type=doc["mime_type"],
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


@app.get("/documents/{doc_id}/facts", response_model=DocumentFactsResponse)
def get_document_facts(doc_id: str) -> dict:
    seed = settings.default_seed
    if cache.get_document(seed, doc_id) is None:
        raise HTTPException(status_code=404, detail="document not found")
    return {"meta": _meta(), "doc_id": doc_id, **cache.get_document_facts(seed, doc_id)}


@app.get("/processors/{processor_id}/reasoning", response_model=ReasoningResponse)
def get_processor_reasoning(processor_id: str) -> dict:
    seed, facts_source = settings.default_seed, settings.default_facts_source
    if cache.get_processor_profile(seed, processor_id) is None:
        raise HTTPException(status_code=404, detail="processor not found")
    assessments = cache.get_processor_assessments(seed, facts_source, processor_id)
    steps = cache.get_reasoning_steps(seed, facts_source, processor_id)
    return {
        "meta": _meta(),
        "processor_id": processor_id,
        "agent_status": assessments["agent_status"] if assessments else None,
        "tool_cap_reached": any(s["step_type"] == "tool_cap_reached" for s in steps),
        "steps": steps,
        "findings": cache.get_findings(seed, facts_source, processor_id),
    }


@app.get("/processors/{processor_id}/site", response_model=SiteResponse)
def get_processor_site(processor_id: str) -> dict:
    seed = settings.default_seed
    if cache.get_processor_profile(seed, processor_id) is None:
        raise HTTPException(status_code=404, detail="processor not found")
    site = cache.get_site_assessment(seed, processor_id)
    if site is None:
        raise HTTPException(status_code=404, detail="site assessment not available")
    return {
        "meta": _meta(),
        "processor_id": processor_id,
        "status": site["status"],
        "severity": site["severity"],
        "measured": site["measured"],
        "threshold": site["threshold"],
        "building_count": site["building_count"],
        "total_footprint_m2": site["total_footprint_m2"],
        # Project rule: never display coordinates with more than 2dp.
        "thumb_bbox": [
            round(site["thumb_bbox_w"], 2),
            round(site["thumb_bbox_s"], 2),
            round(site["thumb_bbox_e"], 2),
            round(site["thumb_bbox_n"], 2),
        ],
        "thumb_crs": site["thumb_crs"],
        "explanation": site["explanation"],
        "sentinel_attribution": geo_site.SENTINEL_ATTRIBUTION,
        "open_buildings_attribution": geo_site.OPEN_BUILDINGS_ATTRIBUTION,
    }


@app.get("/site-images/{processor_id}")
def get_site_image(processor_id: str) -> Response:
    """Same validation-before-read pattern as /documents/{doc_id}/file —
    the GCS blob path always comes from the looked-up row."""
    site = cache.get_site_assessment(settings.default_seed, processor_id)
    if site is None or not site.get("thumbnail_gcs_path"):
        raise HTTPException(status_code=404, detail="site thumbnail not available")
    data = gcs.download_bytes(
        gcs.get_client(), settings.artifact_bucket, site["thumbnail_gcs_path"]
    )
    return Response(
        content=data,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


@app.get("/portfolio/{brand_id}", response_model=PortfolioResponse)
def get_portfolio(brand_id: str) -> dict:
    seed, facts_source = settings.default_seed, settings.default_facts_source
    brand = cache.get_brand(seed, brand_id)
    if brand is None:
        raise HTTPException(status_code=404, detail="brand not found")

    certificates = cache.get_certificates_for_brand(seed, brand_id)
    assessment_by_processor: dict[str, dict | None] = {}
    rows = []
    total_certified_t = 0.0
    total_verifiable_t = 0.0
    for cert in certificates:
        pid = cert["processor_id"]
        if pid not in assessment_by_processor:
            assessment_by_processor[pid] = cache.get_processor_assessments(seed, facts_source, pid)
        assessments = assessment_by_processor[pid]
        # Prefer the "full" stage (checks + agents) when it exists, else
        # fall back to "checks_only" — see docs/ARCHITECTURE.md §7's
        # apportionment note: this ratio is derived, not a traced
        # per-certificate figure (no scoring happens below the processor/
        # FY-to-date level anywhere upstream).
        stage = (assessments or {}).get("full") or (assessments or {}).get("checks_only")
        risk_band = stage["risk_band"] if stage else None
        ratio = (
            stage["verifiable_t"] / stage["certified_t"] if stage and stage["certified_t"] else 0.0
        )

        total_certified_t += cert["quantity_t"]
        total_verifiable_t += cert["quantity_t"] * ratio
        rows.append(
            {
                "certificate_id": cert["certificate_id"],
                "processor_id": pid,
                "category": cert["category"],
                "quantity_t": cert["quantity_t"],
                "period_month": cert["period_month"],
                "processor_risk_band": risk_band,
            }
        )

    return {
        "meta": _meta(),
        "brand_id": brand_id,
        "brand_name": brand["name"],
        "total_certified_t": round(total_certified_t, 2),
        "total_verifiable_t": round(total_verifiable_t, 2),
        "certificates": rows,
    }


@app.get("/evaluation", response_model=EvaluationResponse)
def get_evaluation() -> dict:
    """eval_results isn't in app/store/bq.py's SCHEMAS yet (T14 adds it) —
    this never queries BigQuery at all, so there's no table-not-found
    failure mode to handle."""
    return {"meta": _meta()}


@app.get("/alerts", response_model=AlertsResponse)
def get_alerts() -> dict:
    """The alerts table doesn't exist yet (T13 creates it) — same reasoning
    as /evaluation above."""
    return {"meta": _meta()}
