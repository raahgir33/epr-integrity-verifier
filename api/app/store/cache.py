"""In-process read cache for API responses (docs/ARCHITECTURE.md §7).

Every GET route in app/main.py reads through here, never queries BigQuery
directly. app/main.py's startup hook calls preload() once for the one
configured (seed, facts_source) (app/config.py's default_seed/
default_facts_source — "never mix sources in a response"), so in practice
every request after boot is a cache hit; get_or_load's TTL/loader path
below also serves any key a lazy call misses (e.g. a specific doc_id's
facts, not worth preloading in full) and is what a future live-update path
(T13) would re-populate after invalidate().

Table sizes for seed 42 are small (10 processors, ~150 shipments, ~700
documents, ~150 check_results/agent_runs rows) — caching whole tables per
(seed[, facts_source]) and filtering in Python is simpler and just as fast
as per-processor queries, and lets every per-processor read share one
cached fetch instead of one query each.
"""

import collections
import json
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from google.cloud import bigquery

from app.agents.orchestrator import reconstruct_agent_findings
from app.agents.scorer import score_processor
from app.checks.duplicates import find_duplicate_keys
from app.checks.mass_balance import verified_inbound_tonnes
from app.checks.params import CHECK_SOURCE_LABELS
from app.config import settings
from app.models.checks import CheckResult
from app.store import bq, gcs

logger = logging.getLogger(__name__)

# A2 (docs/PROGRESS.md): every preload-populated key uses this instead of
# settings.cache_ttl_seconds — a short wall-clock TTL was silently
# undermining "preload once, stay warm," since any read made more than
# cache_ttl_seconds after startup re-triggered a live BigQuery query
# regardless of preload having already run (the measured cause of a
# 10.9s "cold" /processors/{id} request well after boot). Nothing in
# this dataset changes during the process's lifetime except through an
# explicit invalidate() call (T13's live event path) — wall-clock
# staleness was never the right trigger for this data.
NO_EXPIRY = float("inf")

_store: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()


def get_or_load(key: str, loader: Callable[[], Any], ttl: int | None = None) -> Any:
    ttl = settings.cache_ttl_seconds if ttl is None else ttl
    now = time.monotonic()
    with _lock:
        cached = _store.get(key)
        if cached is not None and now - cached[0] < ttl:
            return cached[1]
    value = loader()
    with _lock:
        _store[key] = (now, value)
    return value


def invalidate(key: str | None = None) -> None:
    """None clears everything; a specific key clears just that one. Not
    called anywhere in T11 — exposed for T13's live event path, which
    writes a new assessment and must make the next read see it."""
    with _lock:
        if key is None:
            _store.clear()
        else:
            _store.pop(key, None)


# ---------- BigQuery fetch (one query per table, not per processor) ----------


def _table_ref(table: str) -> str:
    return f"{settings.gcp_project}.{settings.bq_dataset}.{table}"


def _fetch_rows(
    client: bigquery.Client,
    table: str,
    columns: str,
    seed: int,
    facts_source: str | None = None,
) -> list[dict]:
    query = f"SELECT {columns} FROM `{_table_ref(table)}` WHERE seed = @seed"
    params = [bigquery.ScalarQueryParameter("seed", "INTEGER", seed)]
    if facts_source is not None:
        query += " AND facts_source = @facts_source"
        params.append(bigquery.ScalarQueryParameter("facts_source", "STRING", facts_source))
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    job = client.query(query, job_config=job_config, location=settings.vertex_location)
    return [dict(row) for row in job.result()]


def _row_date_to_ddmmyyyy(value) -> str | None:
    """BigQuery DATE columns come back as datetime.date; the rest of the
    codebase (app/checks/, app/ingest/units.py) prints dates as
    "DD/MM/YYYY" — matching that here keeps the API's dates in the same
    format as every other printed-value field."""
    return None if value is None else value.strftime("%d/%m/%Y")


def _row_timestamp_to_iso(value) -> str | None:
    return None if value is None else value.isoformat()


# ---------- whole-table cached loaders ----------


def _processors(seed: int) -> list[dict]:
    return get_or_load(
        f"processors:{seed}",
        lambda: _fetch_rows(
            bq.get_client(),
            "processors",
            "processor_id, name, type, permitted_categories, capacity_t_per_year, "
            "consent_no, consent_valid_from, consent_valid_to, registration_no, gstin, "
            "address, lat, lon",
            seed,
        ),
        ttl=NO_EXPIRY,
    )


def _brands(seed: int) -> list[dict]:
    return get_or_load(
        f"brands:{seed}",
        lambda: _fetch_rows(bq.get_client(), "brands", "brand_id, name", seed),
        ttl=NO_EXPIRY,
    )


def _certificates(seed: int) -> list[dict]:
    def load() -> list[dict]:
        rows = _fetch_rows(
            bq.get_client(),
            "certificates",
            "certificate_id, processor_id, brand_id, category, quantity_t, "
            "generation_date, period_month",
            seed,
        )
        for row in rows:
            row["generation_date"] = _row_date_to_ddmmyyyy(row["generation_date"])
        return rows

    return get_or_load(f"certificates:{seed}", load, ttl=NO_EXPIRY)


def get_all_shipments(seed: int, facts_source: str) -> list[dict]:
    """Every processor's shipments for this (seed, facts_source) — needed
    cross-processor for duplicate_keys (F4's duplicate is only visible
    with a cross-processor view). Exposed publicly: the reasoning-
    reconstruction path (app/agents/orchestrator.py's
    reconstruct_agent_findings) needs this same full set to rebuild
    verified_inbound_shipment_ids exactly as the pipeline computed it."""

    def load() -> list[dict]:
        rows = _fetch_rows(
            bq.get_client(),
            "shipments",
            "shipment_id, processor_id, month, invoice_doc_id, eway_doc_id, "
            "weighbridge_doc_id, invoice_qty_t, weighbridge_net_t, match_status, "
            "ewb_no, vehicle_no, distance_km, eway_generated_at, eway_valid_until, "
            "weighbridge_in_time, invoice_no, supplier_gstin, weighbridge_ticket_no",
            seed,
            facts_source=facts_source,
        )
        for row in rows:
            row["eway_generated_at"] = _row_timestamp_to_iso(row["eway_generated_at"])
            row["eway_valid_until"] = _row_timestamp_to_iso(row["eway_valid_until"])
            row["weighbridge_in_time"] = _row_timestamp_to_iso(row["weighbridge_in_time"])
        return rows

    return get_or_load(f"shipments:{seed}:{facts_source}", load, ttl=NO_EXPIRY)


def _check_results(seed: int, facts_source: str) -> list[dict]:
    def load() -> list[dict]:
        return _fetch_rows(
            bq.get_client(),
            "check_results",
            "processor_id, check_id, status, severity, measured, threshold, "
            "affected_tonnes, evidence_ids, explanation",
            seed,
            facts_source=facts_source,
        )

    return get_or_load(f"check_results:{seed}:{facts_source}", load, ttl=NO_EXPIRY)


def _assessments(seed: int, facts_source: str) -> list[dict]:
    def load() -> list[dict]:
        return _fetch_rows(
            bq.get_client(),
            "assessments",
            "stage, processor_id, certified_t, verified_inbound_t, capacity_limit_t, "
            "verifiable_t, unverifiable_t, risk_band, agent_status",
            seed,
            facts_source=facts_source,
        )

    return get_or_load(f"assessments:{seed}:{facts_source}", load, ttl=NO_EXPIRY)


def _site_assessments(seed: int) -> list[dict]:
    def load() -> list[dict]:
        return _fetch_rows(
            bq.get_client(),
            "site_assessments",
            "processor_id, status, severity, measured, threshold, building_count, "
            "total_footprint_m2, thumbnail_gcs_path, thumb_bbox_w, thumb_bbox_s, "
            "thumb_bbox_e, thumb_bbox_n, thumb_crs, explanation",
            seed,
        )

    return get_or_load(f"site_assessments:{seed}", load, ttl=NO_EXPIRY)


def _documents(seed: int) -> list[dict]:
    return get_or_load(
        f"documents:{seed}",
        lambda: _fetch_rows(
            bq.get_client(),
            "documents",
            "doc_id, processor_id, doc_type, lang, gcs_path, mime_type",
            seed,
        ),
        ttl=NO_EXPIRY,
    )


def _extracted_facts(seed: int) -> list[dict]:
    return get_or_load(
        f"extracted_facts:{seed}",
        lambda: _fetch_rows(
            bq.get_client(),
            "extracted_facts",
            "doc_id, field_name, printed_value, confidence, page",
            seed,
        ),
        ttl=NO_EXPIRY,
    )


def _extraction_results(seed: int) -> list[dict]:
    return get_or_load(
        f"extraction_results:{seed}",
        lambda: _fetch_rows(
            bq.get_client(), "extraction_results", "doc_id, status, error_message", seed
        ),
        ttl=NO_EXPIRY,
    )


def _agent_runs(seed: int, facts_source: str) -> list[dict]:
    def load() -> list[dict]:
        return _fetch_rows(
            bq.get_client(),
            "agent_runs",
            "processor_id, step_index, step_type, tool_name, tool_args_json, "
            "input_summary, output_json, latency_ms, input_tokens, output_tokens, "
            "thinking_tokens",
            seed,
            facts_source=facts_source,
        )

    return get_or_load(f"agent_runs:{seed}:{facts_source}", load, ttl=NO_EXPIRY)


def get_agent_trail(seed: int, facts_source: str, processor_id: str) -> list[dict]:
    """Raw agent_runs rows for one processor, ordered by step_index — the
    shape app/agents/orchestrator.py's reconstruct_agent_findings expects.
    All processors are fetched and cached in one query (the table is
    small); filtering/sorting happens here per call."""
    all_rows = _agent_runs(seed, facts_source)
    return sorted(
        (r for r in all_rows if r["processor_id"] == processor_id), key=lambda r: r["step_index"]
    )


# ---------- public per-entity reads ----------


def list_processors(seed: int, facts_source: str) -> list[dict]:
    """Processors that have at least a checks_only assessment — a
    processor row with no assessment at all means the precompute pipeline
    hasn't scored it for this (seed, facts_source), which this API
    treats as not part of the served dataset (never partially invented)."""
    processors = _processors(seed)
    assessments_by_processor = _assessments_by_processor(seed, facts_source)
    result = []
    for p in processors:
        stages = assessments_by_processor.get(p["processor_id"])
        if stages is None or "checks_only" not in stages:
            continue
        result.append(
            {
                "processor_id": p["processor_id"],
                "name": p["name"],
                "type": p["type"],
                "checks_only": _stage_assessment(stages["checks_only"]),
                "full": _stage_assessment(stages["full"]) if "full" in stages else None,
                "agent_status": stages.get("full", {}).get("agent_status"),
            }
        )
    return result


def _assessments_by_processor(seed: int, facts_source: str) -> dict[str, dict[str, dict]]:
    rows = _assessments(seed, facts_source)
    grouped: dict[str, dict[str, dict]] = {}
    for row in rows:
        grouped.setdefault(row["processor_id"], {})[row["stage"]] = row
    return grouped


def _stage_assessment(row: dict) -> dict:
    return {
        "certified_t": row["certified_t"],
        "verified_inbound_t": row["verified_inbound_t"],
        "capacity_limit_t": row["capacity_limit_t"],
        "verifiable_t": row["verifiable_t"],
        "unverifiable_t": row["unverifiable_t"],
        "risk_band": row["risk_band"],
    }


def get_processor_profile(seed: int, processor_id: str) -> dict | None:
    for p in _processors(seed):
        if p["processor_id"] == processor_id:
            return {
                "processor_id": p["processor_id"],
                "name": p["name"],
                "type": p["type"],
                "capacity_t_per_year": p["capacity_t_per_year"],
                "permitted_categories": p["permitted_categories"],
                "consent_no": p["consent_no"],
                "consent_valid_from": _row_date_to_ddmmyyyy(p["consent_valid_from"]),
                "consent_valid_to": _row_date_to_ddmmyyyy(p["consent_valid_to"]),
                "registration_no": p["registration_no"],
                "gstin": p["gstin"],
                "address": p["address"],
                # Project rule §9: never display coordinates with more than
                # 2 decimal places — enforced at the API layer, not left
                # to whatever renders this later.
                "lat": round(p["lat"], 2) if p["lat"] is not None else None,
                "lon": round(p["lon"], 2) if p["lon"] is not None else None,
            }
    return None


def get_processor_assessments(seed: int, facts_source: str, processor_id: str) -> dict | None:
    """{"checks_only": {...}|None, "full": {...}|None, "agent_status": str|None}."""
    stages = _assessments_by_processor(seed, facts_source).get(processor_id)
    if stages is None:
        return None
    return {
        "checks_only": (
            _stage_assessment(stages["checks_only"]) if "checks_only" in stages else None
        ),
        "full": _stage_assessment(stages["full"]) if "full" in stages else None,
        "agent_status": stages.get("full", {}).get("agent_status"),
    }


def get_check_results(seed: int, facts_source: str, processor_id: str) -> list[dict]:
    rows = [r for r in _check_results(seed, facts_source) if r["processor_id"] == processor_id]
    return [
        {
            "check_id": r["check_id"],
            "status": r["status"],
            "severity": r["severity"],
            "measured": r["measured"],
            "threshold": r["threshold"],
            "affected_tonnes": r["affected_tonnes"],
            "evidence_ids": list(r["evidence_ids"] or []),
            "explanation": r["explanation"],
            "source": CHECK_SOURCE_LABELS.get(r["check_id"], "Unlabeled"),
        }
        for r in rows
    ]


def get_certificates_for_processor(seed: int, processor_id: str) -> list[dict]:
    return [c for c in _certificates(seed) if c["processor_id"] == processor_id]


def get_monthly_flow(seed: int, facts_source: str, processor_id: str) -> list[dict]:
    """Per-month certified and verified-inbound tonnes (that month's own
    slice, not cumulative — mirrors app/agents/orchestrator.py's own
    monthly table, computed independently here rather than reusing that
    agents-specific private helper). Scoped to THIS processor's own
    shipments only — unlike the agent-finding reconstruction path, C5's
    cross-processor duplicate detection doesn't change this processor's
    own monthly figures (a cross-processor duplicate is always resolved
    by excluding the unmatched side via match_status, which duplicate_keys
    computed from this processor's shipments alone already reflects)."""
    shipments = [
        s for s in get_all_shipments(seed, facts_source) if s["processor_id"] == processor_id
    ]
    certificates = get_certificates_for_processor(seed, processor_id)
    duplicate_keys = find_duplicate_keys(shipments)

    months = sorted(
        {c["period_month"] for c in certificates}
        | {s["month"] for s in shipments if s.get("month")}
    )
    rows = []
    for month in months:
        certified_t = sum(c["quantity_t"] for c in certificates if c["period_month"] == month)
        month_shipments = [s for s in shipments if s.get("month") == month]
        verified_inbound_t = verified_inbound_tonnes(month_shipments, duplicate_keys)
        rows.append(
            {
                "month": month,
                "certified_t": round(certified_t, 2),
                "verified_inbound_t": round(verified_inbound_t, 2),
            }
        )
    return rows


def get_documents_for_processor(seed: int, processor_id: str) -> list[dict]:
    extraction_status_by_doc = {r["doc_id"]: r["status"] for r in _extraction_results(seed)}
    return [
        {
            "doc_id": d["doc_id"],
            "doc_type": d["doc_type"],
            "lang": d["lang"],
            "extraction_status": extraction_status_by_doc.get(d["doc_id"], "not_extracted"),
        }
        for d in _documents(seed)
        if d["processor_id"] == processor_id
    ]


def get_document(seed: int, doc_id: str) -> dict | None:
    """Validates doc_id against the documents table for this seed before
    any GCS read (docs/BUILD_PLAN.md T11) — no arbitrary paths."""
    for d in _documents(seed):
        if d["doc_id"] == doc_id:
            return d
    return None


# A2: document file bytes, LRU-cached (not eagerly preloaded in full —
# ~496 documents is too large to assume will always fit comfortably in
# memory, unlike the ten site thumbnails below). Bounded by total bytes,
# not entry count, since a weighbridge PNG and an invoice PDF differ
# widely in size.
_DOCUMENT_FILE_CACHE_MAX_BYTES = 200 * 1024 * 1024  # 200 MB
_document_file_cache: collections.OrderedDict[str, tuple[bytes, str]] = collections.OrderedDict()
_document_file_cache_bytes = 0
_document_file_cache_lock = threading.Lock()


def get_document_file(seed: int, doc_id: str) -> tuple[bytes, str] | None:
    """Returns (data, mime_type), or None if doc_id doesn't exist for this
    seed — doc_id is validated against the documents table (get_document)
    before any GCS read, cache hit or not, so an unknown doc_id never
    reaches gcs.download_bytes (docs/BUILD_PLAN.md T11's no-arbitrary-
    paths guarantee, unchanged by adding this cache in front of it)."""
    global _document_file_cache_bytes
    with _document_file_cache_lock:
        cached = _document_file_cache.get(doc_id)
        if cached is not None:
            _document_file_cache.move_to_end(doc_id)
            return cached

    doc = get_document(seed, doc_id)
    if doc is None:
        return None
    data = gcs.download_bytes(gcs.get_client(), settings.dossier_bucket, doc["gcs_path"])
    result = (data, doc["mime_type"])

    with _document_file_cache_lock:
        _document_file_cache[doc_id] = result
        _document_file_cache.move_to_end(doc_id)
        _document_file_cache_bytes += len(data)
        while _document_file_cache_bytes > _DOCUMENT_FILE_CACHE_MAX_BYTES and _document_file_cache:
            _, (evicted_data, _) = _document_file_cache.popitem(last=False)
            _document_file_cache_bytes -= len(evicted_data)
    return result


def get_document_facts(seed: int, doc_id: str) -> dict:
    """Independent of facts_source — extraction is the same regardless of
    which mode normalize.py used. Empty fields / "not_extracted" if no
    extraction has run for this doc yet (true for most of seed 42's 496
    documents today — only PWP-01's trial has real rows)."""
    result_row = next((r for r in _extraction_results(seed) if r["doc_id"] == doc_id), None)
    fields = [
        {
            "field_name": f["field_name"],
            "printed_value": f["printed_value"],
            "confidence": f["confidence"],
            "page": f["page"],
        }
        for f in _extracted_facts(seed)
        if f["doc_id"] == doc_id
    ]
    if result_row is None:
        return {
            "extraction_status": "not_extracted",
            "error_message": None,
            "fields": fields,
        }
    return {
        "extraction_status": result_row["status"],
        "error_message": result_row["error_message"],
        "fields": fields,
    }


def get_site_assessment(seed: int, processor_id: str) -> dict | None:
    for row in _site_assessments(seed):
        if row["processor_id"] == processor_id:
            return row
    return None


# A2: site thumbnail bytes, eagerly cached in full at startup (preload) —
# unlike documents above, there's only one per processor (ten total for
# seed 42), small enough to always keep in memory rather than bound by an
# LRU. Lazily fills itself too (not just on a cache miss from preload
# never having run for this processor_id — e.g. a processor added after
# startup), so this never depends on preload having already run.
_site_image_cache: dict[str, bytes] = {}
_site_image_cache_lock = threading.Lock()


def get_site_image_bytes(seed: int, processor_id: str) -> bytes | None:
    with _site_image_cache_lock:
        cached = _site_image_cache.get(processor_id)
    if cached is not None:
        return cached

    site = get_site_assessment(seed, processor_id)
    if site is None or not site.get("thumbnail_gcs_path"):
        return None
    data = gcs.download_bytes(
        gcs.get_client(), settings.artifact_bucket, site["thumbnail_gcs_path"]
    )
    with _site_image_cache_lock:
        _site_image_cache[processor_id] = data
    return data


def get_brand(seed: int, brand_id: str) -> dict | None:
    for b in _brands(seed):
        if b["brand_id"] == brand_id:
            return b
    return None


def list_brands(seed: int) -> list[dict]:
    """T12: lets /portfolio offer a brand picker without an ID already in
    hand. Sorted by brand_id for a stable listing order."""
    return sorted(_brands(seed), key=lambda b: b["brand_id"])


def get_certificates_for_brand(seed: int, brand_id: str) -> list[dict]:
    return [c for c in _certificates(seed) if c["brand_id"] == brand_id]


# ---------- agent-reconstruction context (processor detail + reasoning) ----------


def build_reconstruction_context(seed: int, facts_source: str, processor_id: str) -> dict | None:
    """processor_context shaped for app/agents/orchestrator.py's
    reconstruct_agent_findings/classify_confirmed_findings — built from
    CURRENT BigQuery data (never from ground_truth.json; the API never
    reads that file). documents here carry only doc_id/doc_type (no
    printed `fields`) — confirmed sufficient: the reconstruction path only
    ever needs doc_id -> doc_type to validate evidence_ids and classify
    own-evidence, never a document's content."""
    profile = get_processor_profile(seed, processor_id)
    if profile is None:
        return None
    all_shipments = get_all_shipments(seed, facts_source)
    return {
        "processor": {
            "processor_id": processor_id,
            "capacity_t_per_year": profile["capacity_t_per_year"],
            "permitted_categories": profile["permitted_categories"],
            "consent_valid_from": profile["consent_valid_from"],
            "consent_valid_to": profile["consent_valid_to"],
        },
        "shipments": [s for s in all_shipments if s["processor_id"] == processor_id],
        "duplicate_keys": find_duplicate_keys(all_shipments),
        "check_results": get_check_results(seed, facts_source, processor_id),
        "documents": [
            {"doc_id": d["doc_id"], "doc_type": d["doc_type"]}
            for d in _documents(seed)
            if d["processor_id"] == processor_id
        ],
    }


def get_findings(seed: int, facts_source: str, processor_id: str) -> list[dict]:
    """Rebuilds the full agent finding list + classification for this
    processor from its stored agent_runs trail (docs/BUILD_PLAN.md T11 —
    classification was never persisted, only its aggregate scoring
    effect). Returns [] if no agent run exists for this processor yet.
    Cached (A2) — this reconstruction is cheap but non-trivial (JSON
    parsing + classification logic), and "every cache the endpoints use
    is filled" at preload means this result itself, not just the raw
    tables it's built from."""
    return get_or_load(
        f"findings:{seed}:{facts_source}:{processor_id}",
        lambda: _compute_findings(seed, facts_source, processor_id),
        ttl=NO_EXPIRY,
    )


def _compute_findings(seed: int, facts_source: str, processor_id: str) -> list[dict]:
    trail = get_agent_trail(seed, facts_source, processor_id)
    if not trail:
        return []
    context = build_reconstruction_context(seed, facts_source, processor_id)
    if context is None:
        return []
    reconstructed = reconstruct_agent_findings(trail, context)
    out = []
    for entry in reconstructed["findings"]:
        finding = entry["finding"]
        verdict = entry["verdict"]
        revision = entry["revision"]
        out.append(
            {
                "finding_type": finding.finding_type,
                "classification": entry["classification"],
                "effect": finding.effect,
                "cited_shipment_ids": finding.cited_shipment_ids,
                "evidence_ids": finding.evidence_ids,
                "explanation": finding.explanation,
                "origin": entry["origin"],
                "proposed_by": entry["origin"],
                "verdict": (
                    {"by": "critic", "verdict": verdict.verdict, "reason": verdict.reason}
                    if verdict is not None
                    else None
                ),
                "disputed_by": (
                    {
                        "by": "hypothesis",
                        "decision": getattr(revision, "decision", None)
                        or ("accept" if getattr(revision, "accepted", False) else "reject"),
                        "explanation": revision.explanation,
                    }
                    if revision is not None
                    else None
                ),
            }
        )
    return out


def get_reasoning_steps(seed: int, facts_source: str, processor_id: str) -> list[dict]:
    """The step-by-step trail for the reasoning-trail UI (docs/
    ARCHITECTURE.md §4's "step-by-step timeline"). Cached (A2), same
    reasoning as get_findings above."""
    return get_or_load(
        f"reasoning_steps:{seed}:{facts_source}:{processor_id}",
        lambda: _compute_reasoning_steps(seed, facts_source, processor_id),
        ttl=NO_EXPIRY,
    )


# A2: internal GCS/doc-id storage paths that must never reach an API
# response — found in practice on get_site_assessment's tool result
# (the stored site_assessments row, including thumbnail_gcs_path, is
# exactly what the live agent run saw and so is exactly what's baked
# into that step's stored output_json).
_INTERNAL_PATH_KEYS = {"thumbnail_gcs_path", "gcs_path"}


def _strip_internal_paths(value):
    if isinstance(value, dict):
        return {
            k: _strip_internal_paths(v) for k, v in value.items() if k not in _INTERNAL_PATH_KEYS
        }
    if isinstance(value, list):
        return [_strip_internal_paths(v) for v in value]
    return value


def _parse_tool_result_text(text: str):
    """A tool's result is always a JSON-encoded string today (app/agents/
    tools.py's _cap() always json.dumps()s it) — except the "already
    returned in call N" dedup-hit message (app/llm.py's run_tool_loop),
    which is plain text, and a _cap()-truncated result, which is no
    longer valid JSON. Both fall back to the raw string rather than
    raising or being silently dropped."""
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return text


def _one_line_summary(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= 160 else text[:160] + "..."


def _step_tokens(row: dict) -> dict:
    return {
        "input": row.get("input_tokens"),
        "output": row.get("output_tokens"),
        "thinking": row.get("thinking_tokens"),
    }


def _reasoning_step(step_index: int, step_type: str, **fields) -> dict:
    base = {
        "step_index": step_index,
        "step_type": step_type,
        "tool_name": None,
        "tool_args": None,
        "output": None,
        "result": None,
        "result_summary": None,
        "latency_ms": None,
        "tokens": {"input": None, "output": None, "thinking": None},
        "dedup_hit": False,
    }
    base.update(fields)
    return base


def _merge_tool_steps(trail: list[dict]) -> list[dict]:
    """Merges each critic_tool_call row with its following critic_tool_
    result row(s) into one step_type="critic_tool" step (docs/
    BUILD_PLAN.md A2): {tool_name, tool_args, result (the tool's own
    parsed return value, internal storage paths stripped), result_summary
    (one line), dedup_hit}. A read_document call's attachment Content
    also lands as a SECOND critic_tool_result row (inline_data, no
    function_response) immediately after the first — folded into the
    same merged step silently, since read_document's own text summary
    already says "document attached"; it would otherwise become an
    orphan step with no tool_name. Every other step_type passes through
    with its existing output_json parsed into `output`."""
    steps: list[dict] = []
    i = 0
    while i < len(trail):
        row = trail[i]
        if row["step_type"] != "critic_tool_call":
            output = json.loads(row["output_json"]) if row.get("output_json") else None
            steps.append(
                _reasoning_step(
                    row["step_index"],
                    row["step_type"],
                    output=output,
                    latency_ms=row.get("latency_ms"),
                    tokens=_step_tokens(row),
                )
            )
            i += 1
            continue

        tool_args = json.loads(row["tool_args_json"]) if row.get("tool_args_json") else None
        result = None
        result_summary = None
        dedup_hit = False
        j = i + 1
        consumed = False
        while j < len(trail) and trail[j]["step_type"] == "critic_tool_result":
            output = json.loads(trail[j]["output_json"]) if trail[j].get("output_json") else None
            parts = (output or {}).get("parts") or []
            function_response = next(
                (
                    p.get("function_response")
                    for p in parts
                    if isinstance(p, dict) and "function_response" in p
                ),
                None,
            )
            if function_response is not None and not consumed:
                raw = function_response.get("result")
                if isinstance(raw, str):
                    dedup_hit = "Already returned in call" in raw
                    parsed = _parse_tool_result_text(raw)
                else:
                    parsed = raw
                result = _strip_internal_paths(parsed)
                result_summary = _one_line_summary(result)
                consumed = True
            j += 1

        steps.append(
            _reasoning_step(
                row["step_index"],
                "critic_tool",
                tool_name=row.get("tool_name"),
                tool_args=tool_args,
                result=result,
                result_summary=result_summary,
                dedup_hit=dedup_hit,
                latency_ms=row.get("latency_ms"),
                tokens=_step_tokens(row),
            )
        )
        i = j
    return steps


def _compute_reasoning_steps(seed: int, facts_source: str, processor_id: str) -> list[dict]:
    trail = get_agent_trail(seed, facts_source, processor_id)
    steps = _merge_tool_steps(trail)
    next_index = max((s["step_index"] for s in steps), default=-1) + 1

    # A2: a run with nothing to revise (no disputed Hypothesis findings,
    # no new Critic objections) never calls the revision round at all —
    # app/agents/orchestrator.py's run_agent_loop skips it entirely, so
    # no "revision" trail row exists. Make that explicit rather than
    # leaving a silent gap in the timeline.
    if trail and not any(s["step_type"] == "revision" for s in steps):
        steps.append(
            _reasoning_step(
                next_index,
                "revision",
                output={
                    "note": (
                        "not needed — no disputed findings or new Critic "
                        "objections required a revision round"
                    )
                },
            )
        )
        next_index += 1

    # A2: a final "score" step from the stored assessments — checks_only
    # vs full verifiable_t, exactly which shipments were deducted (with
    # their own tonnage) and why, and the risk band before/after the
    # agent stage. Only added once an agent run has actually happened for
    # this processor (a "full" assessment stage exists).
    assessments = get_processor_assessments(seed, facts_source, processor_id)
    if assessments is not None:
        context = build_reconstruction_context(seed, facts_source, processor_id)
        excluded_ids: frozenset[str] = frozenset()
        if trail and context is not None:
            excluded_ids = reconstruct_agent_findings(trail, context)["excluded_shipment_ids"]
        shipments_by_id = {s["shipment_id"]: s for s in (context["shipments"] if context else [])}
        deducted_shipments = [
            {
                "shipment_id": shipment_id,
                "weighbridge_net_t": shipments_by_id[shipment_id].get("weighbridge_net_t"),
            }
            for shipment_id in sorted(excluded_ids)
            if shipment_id in shipments_by_id
        ]
        checks_only = assessments.get("checks_only")
        full = assessments.get("full")
        steps.append(
            _reasoning_step(
                next_index,
                "score",
                output={
                    "checks_only_verifiable_t": checks_only["verifiable_t"]
                    if checks_only
                    else None,
                    "full_verifiable_t": full["verifiable_t"] if full else None,
                    "deducted_shipments": deducted_shipments,
                    "risk_band_before": checks_only["risk_band"] if checks_only else None,
                    "risk_band_after": (full or checks_only or {}).get("risk_band"),
                },
            )
        )

    return steps


def get_as_of_month(seed: int) -> str:
    """The same run-level as_of_month scripts/run_pipeline.py defaults to
    when scoring: the max period_month across every certificate for this
    seed (certificates aren't facts_source-dimensioned). Not stored on the
    assessments row itself, so the consistency check below derives it the
    same way the pipeline did rather than guessing a different source."""
    return max(c["period_month"] for c in _certificates(seed))


# ---------- consistency guard ----------


def check_consistency(seed: int, facts_source: str) -> dict:
    """For every processor with a stored stage="full" assessment,
    reconstructs its agent findings from the stored agent_runs trail and
    recomputes score_processor with the resulting excluded_shipment_ids —
    the recomputed verifiable_t must equal the stored one exactly (within
    float rounding). A mismatch means the read-path reconstruction
    (app/agents/orchestrator.py's reconstruct_agent_findings) has drifted
    from what the live pipeline actually scored — logged as an error here
    (docs/BUILD_PLAN.md T11), not just silently reported, since nothing
    else would ever surface it.

    Returns {"ok": bool, "mismatches": [{"processor_id", "stored_verifiable_t",
    "recomputed_verifiable_t"}]}. Checked once at startup (app/main.py's
    lifespan, after preload) and exposed via GET /health's consistency_ok;
    callable again any time (e.g. from a test) against whatever's
    currently cached."""
    as_of_month = get_as_of_month(seed)
    mismatches = []
    for processor_id, stages in _assessments_by_processor(seed, facts_source).items():
        full = stages.get("full")
        if full is None:
            continue
        profile = get_processor_profile(seed, processor_id)
        context = build_reconstruction_context(seed, facts_source, processor_id)
        if profile is None or context is None:
            continue
        trail = get_agent_trail(seed, facts_source, processor_id)
        reconstructed = reconstruct_agent_findings(trail, context)
        check_result_models = [
            CheckResult(**{k: v for k, v in c.items() if k != "source"})
            for c in context["check_results"]
        ]
        score = score_processor(
            {
                "processor_id": processor_id,
                "capacity_t_per_year": profile["capacity_t_per_year"],
                "permitted_categories": profile["permitted_categories"],
                "consent_valid_from": profile["consent_valid_from"],
                "consent_valid_to": profile["consent_valid_to"],
            },
            get_certificates_for_processor(seed, processor_id),
            context["shipments"],
            context["duplicate_keys"],
            check_result_models,
            as_of_month,
            excluded_shipment_ids=reconstructed["excluded_shipment_ids"],
        )
        recomputed_verifiable_t = score["verifiable_t"]
        stored_verifiable_t = full["verifiable_t"]
        if abs(recomputed_verifiable_t - stored_verifiable_t) > 0.01:
            mismatches.append(
                {
                    "processor_id": processor_id,
                    "stored_verifiable_t": stored_verifiable_t,
                    "recomputed_verifiable_t": recomputed_verifiable_t,
                }
            )

    if mismatches:
        logger.error(
            "consistency check failed for seed=%s facts_source=%s: %s",
            seed,
            facts_source,
            mismatches,
        )
    return {"ok": not mismatches, "mismatches": mismatches}


# ---------- startup preload ----------


def preload(seed: int, facts_source: str) -> None:
    """True eager preload (A2): every cache key app/main.py's routes
    actually read — not just the raw tables, but every per-processor
    derived result built from them (findings reconstruction, reasoning
    steps, monthly flow, etc.) and every file (site images in full;
    documents are an LRU, populated on demand — see get_document_file) —
    is filled here, before app/main.py's lifespan reports the app ready.
    Logs total elapsed time; report this when restarting the server."""
    start = time.monotonic()
    logger.info("preloading cache for seed=%s facts_source=%s", seed, facts_source)

    processors = _processors(seed)
    _brands(seed)
    _certificates(seed)
    get_all_shipments(seed, facts_source)
    _check_results(seed, facts_source)
    _assessments(seed, facts_source)
    _site_assessments(seed)
    _documents(seed)
    _extracted_facts(seed)
    _extraction_results(seed)
    _agent_runs(seed, facts_source)

    for p in processors:
        pid = p["processor_id"]
        get_processor_profile(seed, pid)
        get_processor_assessments(seed, facts_source, pid)
        get_monthly_flow(seed, facts_source, pid)
        get_check_results(seed, facts_source, pid)
        get_documents_for_processor(seed, pid)
        get_findings(seed, facts_source, pid)
        get_reasoning_steps(seed, facts_source, pid)
        get_site_image_bytes(seed, pid)

    elapsed = time.monotonic() - start
    logger.info("cache preload done in %.2fs", elapsed)
