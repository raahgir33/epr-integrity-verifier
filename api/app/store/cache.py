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
from app.store import bq

logger = logging.getLogger(__name__)

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
    )


def _brands(seed: int) -> list[dict]:
    return get_or_load(
        f"brands:{seed}",
        lambda: _fetch_rows(bq.get_client(), "brands", "brand_id, name", seed),
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

    return get_or_load(f"certificates:{seed}", load)


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

    return get_or_load(f"shipments:{seed}:{facts_source}", load)


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

    return get_or_load(f"check_results:{seed}:{facts_source}", load)


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

    return get_or_load(f"assessments:{seed}:{facts_source}", load)


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

    return get_or_load(f"site_assessments:{seed}", load)


def _documents(seed: int) -> list[dict]:
    return get_or_load(
        f"documents:{seed}",
        lambda: _fetch_rows(
            bq.get_client(),
            "documents",
            "doc_id, processor_id, doc_type, lang, gcs_path, mime_type",
            seed,
        ),
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
    )


def _extraction_results(seed: int) -> list[dict]:
    return get_or_load(
        f"extraction_results:{seed}",
        lambda: _fetch_rows(
            bq.get_client(), "extraction_results", "doc_id, status, error_message", seed
        ),
    )


def get_agent_trail(seed: int, facts_source: str, processor_id: str) -> list[dict]:
    """Raw agent_runs rows for one processor, ordered by step_index — the
    shape app/agents/orchestrator.py's reconstruct_agent_findings expects.
    All processors are fetched and cached in one query (the table is
    small); filtering/sorting happens here per call."""

    def load_all() -> list[dict]:
        rows = _fetch_rows(
            bq.get_client(),
            "agent_runs",
            "processor_id, step_index, step_type, tool_name, tool_args_json, "
            "input_summary, output_json, latency_ms, input_tokens, output_tokens, "
            "thinking_tokens",
            seed,
            facts_source=facts_source,
        )
        return rows

    all_rows = get_or_load(f"agent_runs:{seed}:{facts_source}", load_all)
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


def get_brand(seed: int, brand_id: str) -> dict | None:
    for b in _brands(seed):
        if b["brand_id"] == brand_id:
            return b
    return None


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
    effect). Returns [] if no agent run exists for this processor yet."""
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
    ARCHITECTURE.md §4's "step-by-step timeline"). dedup_hit marks a
    critic_tool_call step whose tool result text matches the "already
    returned" cache-hit message app/llm.py's run_tool_loop emits for a
    repeated call — a marker for the UI, not re-derived logic."""
    trail = get_agent_trail(seed, facts_source, processor_id)
    steps = []
    for row in trail:
        output = json.loads(row["output_json"]) if row.get("output_json") else None
        tool_args = json.loads(row["tool_args_json"]) if row.get("tool_args_json") else None
        dedup_hit = False
        if row["step_type"] == "critic_tool_result" and isinstance(output, dict):
            parts = output.get("parts") or []
            for part in parts:
                response = part.get("function_response")
                if isinstance(response, dict) and "Already returned in call" in str(response):
                    dedup_hit = True
        steps.append(
            {
                "step_index": row["step_index"],
                "step_type": row["step_type"],
                "tool_name": row["tool_name"],
                "tool_args": tool_args,
                "output": output,
                "latency_ms": row["latency_ms"],
                "tokens": {
                    "input": row["input_tokens"],
                    "output": row["output_tokens"],
                    "thinking": row["thinking_tokens"],
                },
                "dedup_hit": dedup_hit,
            }
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
    """Populates every cache key this module's read functions use, for the
    one configured (seed, facts_source) — called once from app/main.py's
    startup hook so every request after boot is a cache hit."""
    logger.info("preloading cache for seed=%s facts_source=%s", seed, facts_source)
    _processors(seed)
    _brands(seed)
    _certificates(seed)
    get_all_shipments(seed, facts_source)
    _check_results(seed, facts_source)
    _assessments(seed, facts_source)
    _site_assessments(seed)
    _documents(seed)
    _extracted_facts(seed)
    _extraction_results(seed)
    get_or_load(
        f"agent_runs:{seed}:{facts_source}",
        lambda: _fetch_rows(
            bq.get_client(),
            "agent_runs",
            "processor_id, step_index, step_type, tool_name, tool_args_json, "
            "input_summary, output_json, latency_ms, input_tokens, output_tokens, "
            "thinking_tokens",
            seed,
            facts_source=facts_source,
        ),
    )
    logger.info("cache preload done")
