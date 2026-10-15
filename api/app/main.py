"""FastAPI app and routes (docs/ARCHITECTURE.md §7). Every GET route reads
through app/store/cache.py, never BigQuery/GCS directly except for the two
file-streaming routes (and T13's live-event routes below, which read the
runs/alerts/demo_batches tables directly — small, low-traffic, not part
of the warm read-cache contract preload() guarantees for everything
else).
"""

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Path, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.admin import reset_demo as admin_reset_demo
from app.checks import params as check_params
from app.config import settings
from app.events import pubsub
from app.events import run_processor as live_run_processor
from app.geo import site as geo_site
from app.models.api import (
    AlertsResponse,
    BrandsResponse,
    DemoBatchesResponse,
    DemoCertificateBatchRequest,
    DemoCertificateBatchResponse,
    DocumentFactsResponse,
    DocumentsResponse,
    EvaluationResponse,
    MemoResponse,
    PortfolioResponse,
    ProcessorDetailResponse,
    ProcessorListResponse,
    ReasoningResponse,
    RunStatusOut,
    SiteResponse,
    StatsResponse,
)
from app.store import bq, cache
from app.validation import BRAND_ID_PATTERN, DOC_ID_PATTERN, PROCESSOR_ID_PATTERN

logger = logging.getLogger(__name__)

# T13.8: shared path-parameter types so every route validates the same way
# (FastAPI returns 422 on a mismatch before any cache lookup runs).
ProcessorIdPath = Annotated[str, Path(pattern=PROCESSOR_ID_PATTERN)]
DocIdPath = Annotated[str, Path(pattern=DOC_ID_PATTERN)]
BrandIdPath = Annotated[str, Path(pattern=BRAND_ID_PATTERN)]

# Set by the lifespan hook after preload, from cache.check_consistency() —
# whether the reconstructed agent findings reproduce every processor's
# stored stage="full" verifiable_t exactly (docs/BUILD_PLAN.md T11's
# consistency guard). None until the first preload has run.
_consistency_status: dict | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _consistency_status
    start = time.monotonic()
    cache.preload(settings.default_seed, settings.default_facts_source)
    _consistency_status = cache.check_consistency(
        settings.default_seed, settings.default_facts_source
    )
    # A2 (docs/PROGRESS.md): report this when restarting the server — the
    # app isn't ready for traffic until this log line, by design (both
    # calls above are plain synchronous functions, not awaited
    # coroutines, so uvicorn blocks on them before accepting connections).
    logger.info("startup complete in %.2fs (preload + consistency check)", time.monotonic() - start)
    yield


app = FastAPI(title="epr-api", lifespan=lifespan)

# T13.8: browser-facing CORS — explicit allow-list only, never a wildcard.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    allow_credentials=False,
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Per-request ID (echoed to the client and included in every error
    body below, so a report can be matched to a log line) plus baseline
    security response headers (T13.8) — applied to every response, not
    just error ones."""
    request.state.request_id = str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-Id"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Every HTTPException raised in this file already carries a short,
    safe `detail` string (e.g. "processor not found", "invalid push
    token") — never a traceback or internal path — so it's passed through
    as-is, just reshaped into the uniform {error, request_id} body."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "request_id": _request_id(request)},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.info(
        "422 request_id=%s path=%s errors=%s",
        _request_id(request),
        request.url.path,
        exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content={"error": "invalid request", "request_id": _request_id(request)},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: full traceback to logs only, a generic body to the
    client — never a stack trace or internal path over the wire."""
    logger.exception(
        "unhandled exception request_id=%s path=%s", _request_id(request), request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={"error": "internal error", "request_id": _request_id(request)},
    )


def _meta() -> dict:
    return {"seed": settings.default_seed, "facts_source": settings.default_facts_source}


@app.get(
    "/health",
    summary="Service health",
    description=("Liveness check. Returns a status of ok while the service is running."),
)
def health() -> dict:
    """T13.8: deliberately minimal — no version, model, region or project
    ID over the wire. _consistency_status is still computed and logged at
    startup (see lifespan() above) for an operator tailing logs; it's just
    no longer exposed here."""
    return {"status": "ok"}


@app.get(
    "/processors",
    response_model=ProcessorListResponse,
    summary="List processors",
    description=(
        "Every processor in the served dataset, each with both assessment stages side by side — "
        "rule checks alone, and rule checks plus agent validation — and the status of its agent "
        "run. The agent stage is null for a processor the agents have not run on."
    ),
)
def list_processors() -> dict:
    seed, facts_source = settings.default_seed, settings.default_facts_source
    return {"meta": _meta(), "processors": cache.list_processors(seed, facts_source)}


@app.get(
    "/processors/{processor_id}",
    response_model=ProcessorDetailResponse,
    summary="Processor dossier",
    description=(
        "Everything held about one processor: its profile, monthly material flow, every "
        "rule-check result, both assessment stages, and the agent findings. Returns 404 when the "
        "processor is not in the served dataset, or is present but has not been scored."
    ),
)
def get_processor(processor_id: ProcessorIdPath) -> dict:
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


@app.get(
    "/processors/{processor_id}/documents",
    response_model=DocumentsResponse,
    summary="Processor documents",
    description=(
        "The documents belonging to one processor, each with its document type and extraction "
        "status."
    ),
)
def get_processor_documents(processor_id: ProcessorIdPath) -> dict:
    seed = settings.default_seed
    if cache.get_processor_profile(seed, processor_id) is None:
        raise HTTPException(status_code=404, detail="processor not found")
    return {
        "meta": _meta(),
        "processor_id": processor_id,
        "documents": cache.get_documents_for_processor(seed, processor_id),
    }


@app.get(
    "/documents/{doc_id}/file",
    summary="Document file",
    description=(
        "Streams one document's own file. The identifier is checked against the served dataset "
        "before the file is read, so only documents in that dataset can be fetched. Cacheable for "
        "one day."
    ),
)
def get_document_file(doc_id: DocIdPath) -> Response:
    """doc_id is validated against the documents table for the configured
    seed before any GCS read (docs/BUILD_PLAN.md T11) — no arbitrary
    paths; the GCS blob path always comes from the row we looked up, never
    from the request. Served from an LRU in-memory cache after the first
    request for a given doc_id (app/store/cache.py's get_document_file,
    A2) — Cache-Control below also tells the browser not to ask again."""
    result = cache.get_document_file(settings.default_seed, doc_id)
    if result is None:
        raise HTTPException(status_code=404, detail="document not found")
    data, mime_type = result
    return Response(
        content=data,
        media_type=mime_type,
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


@app.get(
    "/documents/{doc_id}/facts",
    response_model=DocumentFactsResponse,
    summary="Document facts",
    description=(
        "The fields read from one document, each with the confidence and page number recorded for "
        "it. Returned regardless of which facts source the service is scoring from."
    ),
)
def get_document_facts(doc_id: DocIdPath) -> dict:
    seed = settings.default_seed
    if cache.get_document(seed, doc_id) is None:
        raise HTTPException(status_code=404, detail="document not found")
    return {"meta": _meta(), "doc_id": doc_id, **cache.get_document_facts(seed, doc_id)}


@app.get(
    "/processors/{processor_id}/reasoning",
    response_model=ReasoningResponse,
    summary="Agent reasoning trail",
    description=(
        "How the agents reached their conclusion for one processor: the opening hypothesis, one "
        "step per critic tool call, the critic's verdicts, the revision round or an explicit note "
        "that none was needed, and a closing score step. The resulting findings are included, as "
        "is whether the critic reached its tool-call limit."
    ),
)
def get_processor_reasoning(processor_id: ProcessorIdPath) -> dict:
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


@app.get(
    "/processors/{processor_id}/memo",
    response_model=MemoResponse,
    summary="Clarification memo",
    description=(
        "The processor's clarification memo when findings were raised, or its verification "
        "statement when none were — exactly one of the two per processor. Use lang to choose "
        "English or Hindi; has_hindi reports whether a Hindi version exists, so a caller asking "
        "for English still knows whether to offer it. Returns 404 when no memo exists for that "
        "processor and language."
    ),
)
def get_processor_memo(processor_id: ProcessorIdPath, lang: Literal["en", "hi"] = "en") -> dict:
    """app/agents/memo.py's clarification memo (flagged processors) or
    verification statement (clean ones) — exactly one document type per
    processor, written by scripts/run_pipeline.py's --stage memo. A
    Hindi ("hi") row only exists when generate_hindi_memo's guards
    passed; has_hindi tells the caller whether to offer the toggle even
    when they requested "en". T13.8: lang's own validation is now
    FastAPI's (422 on anything else), not a manual 400 check."""
    seed, facts_source = settings.default_seed, settings.default_facts_source
    if cache.get_processor_profile(seed, processor_id) is None:
        raise HTTPException(status_code=404, detail="processor not found")
    row = cache.get_memo(seed, facts_source, processor_id, lang)
    if row is None:
        raise HTTPException(status_code=404, detail="memo not available for this processor/lang")
    return {
        "meta": _meta(),
        "processor_id": processor_id,
        "doc_type": row["doc_type"],
        "lang": row["lang"],
        "memo": json.loads(row["memo_json"]),
        "guard_status": row["guard_status"],
        "generated_at": row["generated_at"],
        "has_hindi": cache.get_memo(seed, facts_source, processor_id, "hi") is not None,
    }


@app.get(
    "/processors/{processor_id}/site",
    response_model=SiteResponse,
    summary="Site plausibility",
    description=(
        "What the satellite view of one processor's site shows: the building count and total "
        "footprint found, the measured value against the threshold it was tested against, an "
        "explanation, and the attribution required for the satellite and building-footprint data. "
        "Bounding-box coordinates are rounded to two decimal places."
    ),
)
def get_processor_site(processor_id: ProcessorIdPath) -> dict:
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


@app.get(
    "/site-images/{processor_id}",
    summary="Site thumbnail",
    description=(
        "Streams the processor's satellite thumbnail as a PNG. The identifier is checked against "
        "the served dataset before the image is read. Cacheable for one day."
    ),
)
def get_site_image(processor_id: ProcessorIdPath) -> Response:
    """Same validation-before-read pattern as /documents/{doc_id}/file —
    the GCS blob path always comes from the looked-up row. All ten of
    seed 42's thumbnails are preloaded into memory at startup
    (app/store/cache.py's get_site_image_bytes, A2), so this never hits
    GCS at request time in practice."""
    data = cache.get_site_image_bytes(settings.default_seed, processor_id)
    if data is None:
        raise HTTPException(status_code=404, detail="site thumbnail not available")
    return Response(
        content=data,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


@app.get(
    "/brands",
    response_model=BrandsResponse,
    summary="List brands",
    description=(
        "Every brand in the served dataset, so a caller can pick one before requesting a portfolio."
    ),
)
def list_brands() -> dict:
    """T12: lets the web app offer a brand picker for /portfolio, which
    otherwise only has GET /portfolio/{brand_id} (needs an ID already in
    hand)."""
    return {"meta": _meta(), "brands": cache.list_brands(settings.default_seed)}


@app.get(
    "/portfolio/{brand_id}",
    response_model=PortfolioResponse,
    summary="Brand portfolio",
    description=(
        "One brand's certificates across processors, with its total certified tonnes and the "
        "share of those tonnes that is verifiable. The verifiable share is each certificate's "
        "quantity scaled by its own processor's verifiable ratio, so it is an apportionment "
        "across the brand's certificates rather than a figure traced to each one."
    ),
)
def get_portfolio(brand_id: BrandIdPath) -> dict:
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


@app.get(
    "/evaluation",
    response_model=EvaluationResponse,
    summary="Evaluation results",
    description=(
        "Measured accuracy against the seeded ground-truth datasets — the held-out test set and "
        "the development set the rules were tuned on — as metric rows carrying a numerator and "
        "denominator, together with a plain-language list of the shortfalls those rows imply. "
        "Reports available as false when no held-out results have been computed yet."
    ),
)
def get_evaluation() -> dict:
    """T14: cache.get_evaluation() isolates its own two eval_metrics reads
    (heldout-seed7, dev-seed<N>) — a failure there degrades to an empty/
    unavailable response, same pattern as GET /stats, rather than a 500."""
    return {"meta": _meta(), **cache.get_evaluation()}


@app.get(
    "/stats",
    response_model=StatsResponse,
    summary="Portfolio totals",
    description=(
        "Dataset-wide figures: total certified and unverifiable tonnes, the number of processors, "
        "documents read and fields read, the financial year covered, and the measured field-read "
        "accuracy."
    ),
)
def get_stats() -> dict:
    """T13.6: one cached read (app/store/cache.py's get_stats, warmed at
    startup preload — see preload()'s own docstring) backing the landing
    page's hero/proof-strip figures and the field-read-accuracy tile. No
    BigQuery query at request time, same as every other route here.
    get_stats already isolates the one sub-metric (field-read-accuracy)
    that does issue a live BigQuery read, so a failure here means the
    core totals themselves broke — logged clearly rather than left to
    FastAPI's default 500, since the web client swallows this into a
    silent "figures hidden" state (lib/api.ts's getStats())."""
    seed, facts_source = settings.default_seed, settings.default_facts_source
    try:
        stats = cache.get_stats(seed, facts_source)
    except Exception:
        logger.exception("GET /stats failed for seed=%s facts_source=%s", seed, facts_source)
        raise HTTPException(status_code=500, detail="stats unavailable") from None
    return {"meta": _meta(), **stats}


@app.get(
    "/alerts",
    response_model=AlertsResponse,
    summary="List alerts",
    description=(
        "Alerts raised by live verification runs, each naming the processor, the risk band before "
        "and after, and any newly raised finding."
    ),
)
def get_alerts() -> dict:
    seed, facts_source = settings.default_seed, settings.default_facts_source
    return {"meta": _meta(), "alerts": cache.get_alerts(seed, facts_source)}


@app.get(
    "/demo-batches",
    response_model=DemoBatchesResponse,
    summary="List demo batches",
    description=(
        "The certificate batches the live-verification demo knows about, each flagged with "
        "whether it is enabled for a run. Only an enabled batch can be submitted."
    ),
)
def list_demo_batches() -> dict:
    """Lets the web app offer a batch picker for the live-verification
    button (docs/BUILD_PLAN.md T13)."""
    return {"meta": _meta(), "batches": cache.get_demo_batches(settings.default_seed)}


def _active_or_recent_runs(seed: int) -> list[dict]:
    return bq.fetch_rows(bq.get_client(), "runs", "*", seed)


@app.post(
    "/demo/certificate-batch",
    response_model=DemoCertificateBatchResponse,
    status_code=202,
    summary="Start a verification run",
    description=(
        "Submits one certificate batch for live verification and returns the identifier of the "
        "run it started; poll the run endpoint for progress. This starts real work rather than "
        "returning a stored result. Only allow-listed batch identifiers are accepted, and an "
        "unknown identifier is rejected separately from a known but disabled one. Beyond that, "
        "one run may be in flight at a time, runs are separated by a 60-second cooldown, and no "
        "more than 10 runs are accepted per day; each of those three returns 429."
    ),
)
def post_demo_certificate_batch(body: DemoCertificateBatchRequest) -> dict:
    """Creates a run record and publishes the scripted batch event
    (docs/ARCHITECTURE.md §3.2). Abuse gates (one run at a time, a
    cooldown between runs, a daily cap) protect the public demo button's
    Gemini cost/quota — docs/BUILD_PLAN.md T13."""
    seed, facts_source = settings.default_seed, settings.default_facts_source
    batch = cache.get_demo_batch(seed, body.batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="unknown batch_id")
    # Checked after the lookup, so an id that does not exist still reads
    # 404 and only a real-but-disabled batch reads 400.
    if body.batch_id not in settings.demo_enabled_batch_ids_list:
        # Server-side half of the demo allow-list; the web picker only
        # offers the same batch, but the endpoint is public, so the gate
        # has to live here too. Every other batch in demo_batches is
        # either period_month 2026-04 — which resets the financial year
        # and collapses the processor's certified tonnes to the batch
        # quantity alone (app/checks/capacity.py's certified_t_fy_to_date
        # filters fy_start <= period_month <= as_of) — or has no
        # extra_document_ids to extract. demo_batches itself is left
        # untouched; GET /demo-batches still reports all of them.
        raise HTTPException(
            status_code=400,
            detail=(
                f"batch {body.batch_id} is not enabled for live verification; "
                f"enabled: {', '.join(settings.demo_enabled_batch_ids_list)}"
            ),
        )
    processor_id = batch["processor_id"]

    now = datetime.now(UTC)
    runs = _active_or_recent_runs(seed)
    non_terminal = [
        r
        for r in runs
        if r["status"] not in ("done", "failed")
        and (now - r["created_at"]).total_seconds() < check_params.ACTIVE_RUN_STALE_AFTER_S
    ]
    if non_terminal:
        raise HTTPException(status_code=429, detail="a verification is already running")

    if runs:
        last = max(runs, key=lambda r: r["created_at"])
        elapsed = (now - last["created_at"]).total_seconds()
        if elapsed < check_params.DEMO_COOLDOWN_SECONDS:
            remaining = int(check_params.DEMO_COOLDOWN_SECONDS - elapsed)
            raise HTTPException(
                status_code=429, detail=f"cooldown active — try again in {remaining}s"
            )

    today_count = sum(1 for r in runs if r["created_at"].date() == now.date())
    if today_count >= check_params.DEMO_DAILY_RUN_CAP:
        raise HTTPException(status_code=429, detail="daily demo limit reached for today")

    # T17 (C7-lite): prefer this processor's bundled pre-demo snapshot as
    # the alert decision's "before" state, so run 2 and run 3 report the
    # same real transition run 1 did instead of comparing against what
    # run 1 itself wrote (High vs High, same findings -> no alert at
    # all). Falls back to live state for any processor with no bundled
    # snapshot. Nothing is restored — this only changes what the
    # comparison baseline is.
    snapshot_before = admin_reset_demo.snapshot_before_from_bundle(seed, facts_source, processor_id)
    if snapshot_before is None:
        assessments = cache.get_processor_assessments(seed, facts_source, processor_id)
        full_assessment = (assessments or {}).get("full")
        findings = cache.get_findings(seed, facts_source, processor_id)
        snapshot_before = {
            "risk_band": full_assessment["risk_band"] if full_assessment else None,
            "findings": [
                {
                    "cited_shipment_ids": f["cited_shipment_ids"],
                    "classification": f["classification"],
                }
                for f in findings
            ],
        }

    run_id = str(uuid.uuid4())
    bq_client = bq.get_client()
    bq.load_rows(
        bq_client,
        "runs",
        [
            {
                "run_id": run_id,
                "batch_id": body.batch_id,
                "processor_id": processor_id,
                "seed": seed,
                "facts_source": facts_source,
                "status": "queued",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "stage_timestamps_json": "{}",
                "error_message": None,
                "snapshot_before_json": json.dumps(snapshot_before),
                "alert_id": None,
            }
        ],
    )
    pubsub.publish_certificate_batch(run_id, body.batch_id)
    return {"run_id": run_id, "status": "queued"}


@app.get(
    "/runs/{run_id}",
    response_model=RunStatusOut,
    summary="Verification run status",
    description=(
        "Progress of one verification run: its stage — queued, reading documents, checking, "
        "reasoning, drafting the memo, done or failed — the timestamps of the stages it has "
        "passed, the reasoning steps produced so far, any alert it raised, and an error message "
        "when it failed."
    ),
)
def get_run(run_id: str) -> dict:
    seed, facts_source = settings.default_seed, settings.default_facts_source
    bq_client = bq.get_client()
    row = live_run_processor.get_run(bq_client, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run not found")

    live_steps = live_run_processor.get_active_run_steps(run_id)
    if live_steps is not None:
        steps = live_steps
    elif row["status"] in ("done", "failed"):
        steps = cache.get_reasoning_steps(seed, facts_source, row["processor_id"])
    else:
        steps = []

    alert = None
    if row.get("alert_id"):
        alert_rows = bq.fetch_rows(bq_client, "alerts", "*", seed)
        alert_row = next((a for a in alert_rows if a["alert_id"] == row["alert_id"]), None)
        if alert_row is not None:
            alert = alert_row

    return {
        "meta": _meta(),
        "run_id": row["run_id"],
        "batch_id": row["batch_id"],
        "processor_id": row["processor_id"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "stage_timestamps": json.loads(row.get("stage_timestamps_json") or "{}"),
        "steps": steps,
        "error_message": row.get("error_message"),
        "alert": alert,
    }


@app.post("/events/certificate-batch", include_in_schema=False)
def post_events_certificate_batch(body: dict, token: str | None = None) -> dict:
    """Pub/Sub push endpoint (docs/ARCHITECTURE.md §3.2). Synchronous
    within the request (internal engineering notes §9's CPU-throttling trap) and
    idempotent on run_id — a re-delivered push for an already-terminal
    run is a no-op, never a duplicate alert."""
    if not pubsub.verify_push_token(token):
        raise HTTPException(status_code=401, detail="invalid push token")

    try:
        payload = pubsub.decode_push_envelope(body)
        run_id = payload["run_id"]
    except (KeyError, ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="malformed push envelope") from None
    bq_client = bq.get_client()
    run_row = live_run_processor.get_run(bq_client, run_id)
    if run_row is None:
        # Unknown run_id — ack anyway so Pub/Sub doesn't retry forever on
        # a malformed/stale message; there is nothing to process.
        return {"status": "ignored"}
    if run_row["status"] in ("done", "failed"):
        return {"status": "already processed"}

    live_run_processor.run_certificate_batch(run_id)
    return {"status": "ok"}


@app.post("/admin/reset-demo", include_in_schema=False)
def post_admin_reset_demo(token: str | None = None) -> dict:
    """T13.8: HTTP-reachable equivalent of scripts/reset_demo.py, for a
    Cloud Scheduler nightly job (the deployed container never has
    data/synthetic/ on disk — see app/admin/reset_demo.py). Same
    PUSH_TOKEN gate as the push endpoint. Idempotent: app.admin.
    reset_demo.run_reset_live deletes-then-loads every touched row, so
    calling this twice back-to-back converges to the same state."""
    if not pubsub.verify_push_token(token):
        raise HTTPException(status_code=401, detail="invalid push token")

    seed, facts_source = settings.default_seed, settings.default_facts_source
    restored = admin_reset_demo.run_reset_live(seed)
    cache.invalidate()
    cache.preload(seed, facts_source)
    return {"status": "ok", "processors_restored": restored}
