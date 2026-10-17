"""T13's live event path — the actual verification work the push handler
(app/main.py's POST /events/certificate-batch) runs synchronously inside
the request (internal engineering notes §9's Cloud Run CPU-throttling trap: all work must
finish before the response is sent, never scheduled after it).

Deliberately does NOT import anything from scripts/: api/Dockerfile only
`COPY app ./app` into the deployed image — scripts/ (and data/) never
ship — so this module re-implements the small amount of BigQuery-
fetching glue scripts/run_pipeline.py's fetch_agent_inputs()/
build_processor_context() already have, scoped down to exactly what one
live run needs (extracted mode only, one target processor, plus a seed-
wide shipment read for C5's cross-processor duplicate check). Every
non-trivial piece — shipment matching, checks, scoring, the agent loop,
memo guards — is still the same app/ code scripts/run_pipeline.py calls;
none of it is duplicated here.

Stage order (docs/PROGRESS.md's T13 plan, approved): reading_documents ->
checking -> reasoning (includes the alert decision) -> drafting_memo ->
done|failed. Each stage writes two runs-table updates (delete_by_run_id +
load, per app/store/bq.py's idempotent-rewrite convention) — one when it
starts (status flips, so a polling GET /runs/{run_id} shows it
immediately) and one when it finishes (stage_timestamps gains that
stage's own measured duration, e.g. "Agents reviewing - 74s" in the web
UI). A failed run still reaches status="failed" and returns normally —
the push handler always responds 2xx either way, so PubSub never
retry-storms a genuinely failed run.
"""

import json
import logging
import random
import threading
import time
from datetime import UTC, datetime

from google.api_core.exceptions import TooManyRequests

from app.agents import memo
from app.agents.orchestrator import run_agent_loop_with_retry
from app.agents.scorer import (
    build_disputed_finding_check_result,
    build_no_own_evidence_finding_check_result,
    build_systemic_finding_check_result,
    score_processor,
)
from app.agents.text_guard import clean_model_text
from app.checks import params
from app.checks.duplicates import find_duplicate_keys
from app.checks.runner import run_checks_for_processor
from app.config import settings
from app.geo.site import site_assessment_to_check_result
from app.ingest.extract import extract_all, facts_to_field_rows
from app.ingest.normalize import facts_by_doc_id, match_shipments_from_extracted
from app.llm import GeminiClient
from app.store import bq, cache, gcs

logger = logging.getLogger(__name__)

_RISK_RANK = {"Low": 0, "Medium": 1, "High": 2}
_DEDUCTION_QUALIFYING_CLASSIFICATIONS = {"deductible", "systemic", "no_own_evidence", "review_flag"}

# In-process live-step tracker (A2-style, same reasoning as the rest of
# this codebase's module-level caches): --max-instances=1 is the
# recommended Cloud Run setting for exactly this reason (docs/PROGRESS.md
# T13 plan §9) — one process, one in-flight run at a time (enforced
# separately by app/main.py's abuse gates), so a plain module-level dict
# is sufficient; no cross-instance coordination is attempted or needed.
_active_runs: dict[str, list[dict]] = {}
_active_runs_lock = threading.Lock()


def get_active_run_steps(run_id: str) -> list[dict] | None:
    """Live reasoning steps for a run still in progress on THIS instance
    — GET /runs/{run_id} (app/main.py) checks this first, before falling
    back to the durable runs/agent_runs tables for a completed run or one
    that ran on a different instance/process lifetime.

    _active_runs stores RAW run_agent_loop trail steps exactly as
    on_step receives them (_trail_step()'s shape: tool_args_json/
    output_json as JSON strings, no tool_args/output/result/
    result_summary/tokens/dedup_hit keys at all) — NOT the API's
    ReasoningStepOut shape. Confirmed live (2026-10-09, docs/
    PROGRESS.md): returning the raw steps straight from this function
    into main.py's response model raised a FastAPI ResponseValidation
    Error (6 missing-field errors) the moment a run reached the
    reasoning stage. Reuses app/store/cache.py's own _merge_tool_steps —
    the exact function the durable read path (get_reasoning_steps)
    already uses to produce this same shape — rather than a second,
    parallel transformation; _merge_tool_steps already tolerates a
    dangling critic_tool_call with no matching critic_tool_result yet
    (the normal case mid-run), so the live, in-progress trail doesn't
    need special-casing."""
    with _active_runs_lock:
        steps = _active_runs.get(run_id)
        if steps is None:
            return None
        return cache._merge_tool_steps(list(steps))


def _row_date_to_ddmmyyyy(value) -> str | None:
    return None if value is None else value.strftime("%d/%m/%Y")


def _row_timestamp_to_iso(value) -> str | None:
    return None if value is None else value.isoformat()


def get_run(bq_client, run_id: str) -> dict | None:
    """settings.default_seed always — the API serves exactly one
    configured seed (docs/ARCHITECTURE.md §7), and every runs row is
    created with that same seed (app/main.py's POST /demo/certificate-
    batch), so a run_id lookup never needs a second seed parameter. Goes
    through bq.fetch_rows (same as every other read in this module)
    rather than a bespoke query, so tests only ever need to fake one
    function.

    created_at/updated_at are converted to ISO strings immediately —
    BigQuery TIMESTAMP columns come back as python datetime objects
    (same reason _row_timestamp_to_iso exists for shipments elsewhere),
    and run_certificate_batch holds onto this same dict and writes it
    straight back to BigQuery at every stage transition (_write_run);
    a raw datetime there breaks load_table_from_json's own JSON
    serialization client-side (confirmed live, 2026-10-09 — see
    docs/PROGRESS.md), which happens *before* the delete-then-load's
    load half ever reaches BigQuery, so the row's prior delete still
    goes through — a failure here silently deletes the run row with no
    replacement, exactly what produced the stuck 404 that surfaced this."""
    rows = bq.fetch_rows(bq_client, "runs", "*", settings.default_seed)
    row = next((r for r in rows if r["run_id"] == run_id), None)
    if row is None:
        return None
    return {
        **row,
        "created_at": _row_timestamp_to_iso(row["created_at"]),
        "updated_at": _row_timestamp_to_iso(row["updated_at"]),
    }


# Runs-row write retry (2026-10-17). Every stage transition rewrites the
# one runs row, and several of those writes land within a few seconds of
# each other, which is enough to trip BigQuery's per-table
# update-operation rate limit: a live run died at
# start_stage("drafting_memo") with 429 rateLimitExceeded ("too many
# table update operations for this table"). Backoff is ~2, 4, 8, 16s plus
# jitter. Deliberately local module privates rather than
# app/checks/params.py entries, same as app/llm.py's own retry budget:
# params.py holds thresholds that change a verification result, and these
# change none.
_RUN_WRITE_MAX_ATTEMPTS = 5
_RUN_WRITE_BASE_BACKOFF_S = 2.0


def _is_rate_limit_error(exc: BaseException) -> bool:
    """TooManyRequests covers the 429 the live run actually raised; the
    reason check also catches a rateLimitExceeded that arrives inside a
    load job's error payload (bq.load_rows re-raises those as a plain
    RuntimeError from job.errors, which carries no HTTP status)."""
    if isinstance(exc, TooManyRequests):
        return True
    errors = getattr(exc, "errors", None) or []
    if any(isinstance(e, dict) and e.get("reason") == "rateLimitExceeded" for e in errors):
        return True
    return "ratelimitexceeded" in str(exc).lower()


def _call_with_rate_limit_retry(what: str, call, *args) -> None:
    """Re-submits `call` from scratch on a BigQuery rate-limit error. A
    load job that failed cannot be re-polled — job.result() has already
    raised — so every attempt is a brand-new job, not a retry of the old
    one. Any other exception propagates on the first attempt."""
    for attempt in range(_RUN_WRITE_MAX_ATTEMPTS):
        try:
            call(*args)
            return
        except Exception as exc:
            if not _is_rate_limit_error(exc) or attempt == _RUN_WRITE_MAX_ATTEMPTS - 1:
                raise
            backoff = _RUN_WRITE_BASE_BACKOFF_S * 2**attempt + random.uniform(0, 1)
            logger.warning(
                "runs-row %s rate-limited (%s) on attempt %d/%d, backing off %.1fs",
                what,
                exc,
                attempt + 1,
                _RUN_WRITE_MAX_ATTEMPTS,
                backoff,
            )
            time.sleep(backoff)


def _write_run(bq_client, run_row: dict) -> None:
    """Delete-then-load rewrite of this run's single row, each half
    retried independently: a rate-limited load must not re-submit the
    delete that already succeeded, since that DML counts against the very
    per-table limit being backed off from. Retrying the pair would still
    be correct (both halves are keyed on run_id) — just more expensive in
    the exact quota that is scarce."""
    _call_with_rate_limit_retry("delete", bq.delete_by_run_id, bq_client, "runs", run_row["run_id"])
    _call_with_rate_limit_retry("load", bq.load_rows, bq_client, "runs", [run_row])


def _get_demo_batch(bq_client, seed: int, batch_id: str) -> dict | None:
    rows = bq.fetch_rows(
        bq_client,
        "demo_batches",
        "batch_id, processor_id, period_month, quantity_t, pushes_over_verifiable, "
        "extra_document_ids",
        seed,
    )
    return next((r for r in rows if r["batch_id"] == batch_id), None)


def _fetch_processor(bq_client, seed: int, processor_id: str) -> dict:
    rows = bq.fetch_rows(
        bq_client,
        "processors",
        "processor_id, name, type, capacity_t_per_year, permitted_categories, "
        "consent_no, consent_valid_from, consent_valid_to, registration_no",
        seed,
        processor_id=processor_id,
    )
    if not rows:
        raise ValueError(f"processor {processor_id} not found for seed {seed}")
    row = rows[0]
    return {
        **row,
        "consent_valid_from": _row_date_to_ddmmyyyy(row["consent_valid_from"]),
        "consent_valid_to": _row_date_to_ddmmyyyy(row["consent_valid_to"]),
    }


_SHIPMENT_COLUMNS = (
    "shipment_id, processor_id, month, invoice_doc_id, eway_doc_id, weighbridge_doc_id, "
    "invoice_qty_t, weighbridge_net_t, match_status, ewb_no, vehicle_no, distance_km, "
    "eway_generated_at, eway_valid_until, weighbridge_in_time, invoice_no, supplier_gstin, "
    "weighbridge_ticket_no"
)


def _fetch_shipments(
    bq_client, seed: int, facts_source: str, processor_id: str | None
) -> list[dict]:
    rows = bq.fetch_rows(
        bq_client,
        "shipments",
        _SHIPMENT_COLUMNS,
        seed,
        processor_id=processor_id,
        facts_source=facts_source,
    )
    return [
        {
            **s,
            "eway_generated_at": _row_timestamp_to_iso(s["eway_generated_at"]),
            "eway_valid_until": _row_timestamp_to_iso(s["eway_valid_until"]),
            "weighbridge_in_time": _row_timestamp_to_iso(s["weighbridge_in_time"]),
        }
        for s in rows
    ]


def _classified_findings(loop_result: dict) -> list[dict]:
    """Flattens run_agent_loop's per-classification finding buckets into
    one list shaped like app/store/cache.py's get_findings (classification
    + cited_shipment_ids + evidence_ids + explanation + finding_type +
    effect) — built directly from this run's own in-memory loop_result,
    never from a stored trail (no reconstruct_agent_findings call needed,
    unlike the read path, since this run's result is already in hand)."""
    flat: list[dict] = []
    for classification, key in (
        ("deductible", "deductible_findings"),
        ("systemic", "systemic_findings"),
        ("no_own_evidence", "no_evidence_findings"),
        ("concurs_with_check", "concurs_with_check_findings"),
        ("review_flag", "review_flag_findings"),
    ):
        for f in loop_result.get(key, []):
            flat.append(
                {
                    "finding_type": f.finding_type,
                    "classification": classification,
                    "effect": f.effect,
                    "cited_shipment_ids": list(f.cited_shipment_ids),
                    "evidence_ids": list(f.evidence_ids),
                    # Guarded here, at the one place these findings enter
                    # the run, so neither the alert's new_finding_summary
                    # nor the memo context can carry a degenerate
                    # repetition (T17). The raw text stays in agent_runs.
                    "explanation": clean_model_text(f.explanation),
                }
            )
    return flat


def _finding_signature(finding: dict) -> tuple:
    return (tuple(sorted(finding["cited_shipment_ids"])), finding["classification"])


def _decide_alert(
    snapshot_before: dict, risk_band_after: str, findings_after: list[dict]
) -> dict | None:
    """Alert fires if risk_band rose, or a new finding appeared whose
    classification would actually affect scoring/visibility
    (_DEDUCTION_QUALIFYING_CLASSIFICATIONS — concurs_with_check and
    withdrawn are deliberately excluded, same as docs/DATA_SPEC.md §4a's
    own neutral treatment of those). None if neither condition holds."""
    risk_band_before = snapshot_before.get("risk_band")
    before_signatures = {_finding_signature(f) for f in snapshot_before.get("findings", [])}
    new_findings = [
        f
        for f in findings_after
        if f["classification"] in _DEDUCTION_QUALIFYING_CLASSIFICATIONS
        and _finding_signature(f) not in before_signatures
    ]
    risk_rose = _RISK_RANK.get(risk_band_after, 0) > _RISK_RANK.get(risk_band_before, 0)
    if not risk_rose and not new_findings:
        return None

    summary = new_findings[0]["explanation"][:200] if new_findings else None
    message = f"Risk band {risk_band_before or 'unknown'} -> {risk_band_after}"
    if summary:
        message += f"; new finding: {summary}"
    return {
        "risk_band_before": risk_band_before,
        "risk_band_after": risk_band_after,
        "new_finding_summary": summary,
        "message": message,
    }


class _RunContext:
    """Tracks the run's row + per-stage timing, writing both runs-table
    updates (stage start, stage finish) each stage transition."""

    def __init__(self, bq_client, run_row: dict):
        self.bq_client = bq_client
        self.run_row = run_row
        self.stage_timestamps: dict = json.loads(run_row.get("stage_timestamps_json") or "{}")
        self._stage_start: float = time.monotonic()

    def _write(self, *, fatal: bool) -> None:
        """Intermediate stage/progress writes are progress reporting, not
        the verification itself: if one still fails after
        _call_with_rate_limit_retry's attempts, the run keeps going and
        the next transition rewrites the whole row anyway (it is a full
        snapshot, so nothing is lost but a few seconds of polling
        freshness). Only finish()'s terminal done/failed write is fatal —
        a run that silently never reaches a terminal status would keep
        the in-flight gate closed until it goes stale."""
        try:
            _write_run(self.bq_client, self.run_row)
        except Exception:
            if fatal:
                raise
            logger.warning(
                "non-fatal runs-row write failed for run_id=%s status=%s — continuing",
                self.run_row["run_id"],
                self.run_row.get("status"),
                exc_info=True,
            )

    def start_stage(self, status: str) -> None:
        self._stage_start = time.monotonic()
        self.run_row["status"] = status
        self.run_row["updated_at"] = datetime.now(UTC).isoformat()
        self._write(fatal=False)

    def finish_stage(self, status: str) -> None:
        duration_s = round(time.monotonic() - self._stage_start, 1)
        self.stage_timestamps[status] = {
            "at": datetime.now(UTC).isoformat(),
            "duration_s": duration_s,
        }
        self.run_row["stage_timestamps_json"] = json.dumps(self.stage_timestamps)
        self.run_row["updated_at"] = datetime.now(UTC).isoformat()
        self._write(fatal=False)

    def publish_alert_id(self, alert_id: str | None) -> None:
        """Puts the alert on the run row as soon as the alerts row itself
        has been written, before finish_stage("reasoning").

        GET /runs/{run_id} only surfaces an alert by resolving the run
        row's alert_id, so until this ran at finish() the alert was
        invisible for the whole drafting_memo stage plus the cache
        re-warm — measured at 39s on the 2026-10-15 run (alert written
        03:29:17, reasoning timestamp 03:29:19, status done 03:29:58).
        The web panel's Alert decision row keys off the reasoning
        timestamp, so it spent those 39s asserting "Risk band unchanged,
        no new finding" about an alert that had already fired Low ->
        High. Writing it here closes the window at the source; the web
        side no longer trusts the reasoning timestamp either (see
        web/lib/runRows.ts).

        Sets the field but does NOT write on its own (2026-10-17): the
        caller runs finish_stage("reasoning") on the very next line, so
        this write and that one landed within ~2s of each other and
        together with the following start_stage("drafting_memo") were
        what tripped BigQuery's per-table update rate limit. Coalescing
        the two costs nothing — the row is a full snapshot and the window
        this method exists to close goes from 39s to the ~2s until that
        finish_stage, not back to the whole memo stage."""
        self.run_row["alert_id"] = alert_id
        self.run_row["updated_at"] = datetime.now(UTC).isoformat()

    def finish(
        self, status: str, error_message: str | None = None, alert_id: str | None = None
    ) -> None:
        self.run_row["status"] = status
        self.run_row["error_message"] = error_message
        if alert_id is not None:
            self.run_row["alert_id"] = alert_id
        self.run_row["updated_at"] = datetime.now(UTC).isoformat()
        self._write(fatal=True)


def run_certificate_batch(run_id: str) -> None:  # noqa: C901
    bq_client = bq.get_client()
    run_row = get_run(bq_client, run_id)
    if run_row is None:
        logger.error("run_certificate_batch: unknown run_id=%s", run_id)
        return
    if run_row["status"] in ("done", "failed"):
        # Idempotency safety net — app/main.py's push handler already
        # checks this before calling in, but a defensive second check
        # here costs nothing and protects any other future caller.
        return

    ctx = _RunContext(bq_client, run_row)
    seed = run_row["seed"]
    facts_source = run_row["facts_source"]
    processor_id = run_row["processor_id"]
    batch_id = run_row["batch_id"]
    snapshot_before = json.loads(run_row.get("snapshot_before_json") or "{}")

    with _active_runs_lock:
        _active_runs[run_id] = []

    def on_step(step: dict) -> None:
        with _active_runs_lock:
            _active_runs.setdefault(run_id, []).append(step)

    try:
        batch = _get_demo_batch(bq_client, seed, batch_id)
        if batch is None:
            raise ValueError(f"demo batch {batch_id} not found for seed {seed}")
        as_of_month = batch["period_month"]
        extra_document_ids = list(batch.get("extra_document_ids") or [])
        gcs_client = gcs.get_client()
        llm_client = GeminiClient()

        # --- 1. reading_documents (skipped if this batch has no new docs) ---
        ctx.start_stage("reading_documents")
        if extra_document_ids:
            doc_rows = bq.fetch_rows(
                bq_client,
                "documents",
                "doc_id, processor_id, doc_type, gcs_path",
                seed,
                processor_id=processor_id,
            )
            new_docs = [d for d in doc_rows if d["doc_id"] in extra_document_ids]
            # A batch that declares extra documents but finds none (or
            # only some) registered must fail here, loudly. extract_all
            # over an empty list returns [] without raising, so this
            # stage used to report "Completed" having read nothing and
            # made zero Gemini calls — the run then added a certificate
            # with no inbound shipment to match it, and the resulting
            # mass-balance shortfall looked like a finding about the
            # processor rather than a broken demo fixture. That is
            # exactly what happened between 2026-10-09 and 2026-10-15,
            # once a reset had removed the `documents` rows (see
            # app/admin/reset_demo.py). Internal engineering notes §7.5:
            # fail visibly, not silently.
            missing = sorted(set(extra_document_ids) - {d["doc_id"] for d in new_docs})
            if missing:
                raise RuntimeError(
                    f"batch {batch_id} declares {len(extra_document_ids)} extra document(s) but "
                    f"{len(missing)} are not registered in the documents table: "
                    f"{', '.join(missing)} — run scripts/load_demo_extra_docs.py --seed {seed}"
                )
            results = extract_all(
                llm_client,
                gcs_client,
                settings.dossier_bucket,
                new_docs,
                purpose_prefix="live_extract",
            )
            extracted_rows = []
            for result in results:
                if result["status"] != "ok":
                    raise RuntimeError(
                        f"extraction failed for {result['doc_id']}: {result.get('error')}"
                    )
                base = {
                    "seed": seed,
                    "doc_id": result["doc_id"],
                    "processor_id": result["processor_id"],
                    "doc_type": result["doc_type"],
                }
                for field_row in facts_to_field_rows(result["facts"]):
                    extracted_rows.append({**base, **field_row})
            bq.delete_by_ids(bq_client, "extracted_facts", "doc_id", extra_document_ids)
            bq.load_rows(bq_client, "extracted_facts", extracted_rows)
        ctx.finish_stage("reading_documents")

        # --- 2. checking ---
        ctx.start_stage("checking")
        processor = _fetch_processor(bq_client, seed, processor_id)
        cert_id = f"CERT-DEMO-{batch_id}"
        bq.delete_by_ids(bq_client, "certificates", "certificate_id", [cert_id])
        bq.load_rows(
            bq_client,
            "certificates",
            [
                {
                    "seed": seed,
                    "certificate_id": cert_id,
                    "processor_id": processor_id,
                    "brand_id": None,
                    "category": processor["permitted_categories"][0],
                    "quantity_t": batch["quantity_t"],
                    "generation_date": datetime.now(UTC).date().isoformat(),
                    "period_month": as_of_month,
                }
            ],
        )

        documents_rows = bq.fetch_rows(
            bq_client,
            "documents",
            "doc_id, processor_id, doc_type, gcs_path",
            seed,
            processor_id=processor_id,
        )
        extracted_rows = bq.fetch_rows(
            bq_client,
            "extracted_facts",
            "doc_id, processor_id, field_name, printed_value",
            seed,
            processor_id=processor_id,
        )
        facts = facts_by_doc_id(extracted_rows)
        shipments_for_processor = match_shipments_from_extracted(
            seed, processor_id, documents_rows, facts
        )
        bq.delete_shipments_by_processor(bq_client, seed, facts_source, processor_id)
        bq.load_rows(
            bq_client,
            "shipments",
            [{"seed": seed, "facts_source": facts_source, **s} for s in shipments_for_processor],
        )

        other_shipments = [
            s
            for s in _fetch_shipments(bq_client, seed, facts_source, None)
            if s["processor_id"] != processor_id
        ]
        all_shipments = other_shipments + shipments_for_processor
        duplicate_keys = find_duplicate_keys(all_shipments)

        certificate_rows = bq.fetch_rows(
            bq_client,
            "certificates",
            "certificate_id, processor_id, category, quantity_t, period_month, generation_date",
            seed,
            processor_id=processor_id,
        )
        certificates = [
            {**c, "generation_date": _row_date_to_ddmmyyyy(c["generation_date"])}
            for c in certificate_rows
        ]
        outputs = bq.fetch_rows(
            bq_client,
            "outputs",
            "doc_id, processor_id, month, quantity_t",
            seed,
            processor_id=processor_id,
            facts_source=facts_source,
        )
        energy_monthly = bq.fetch_rows(
            bq_client,
            "energy_monthly",
            "doc_id, processor_id, month, kwh",
            seed,
            processor_id=processor_id,
            facts_source=facts_source,
        )
        site_rows = bq.fetch_rows(
            bq_client,
            "site_assessments",
            "processor_id, status, severity, measured, threshold, thumbnail_gcs_path, explanation",
            seed,
            processor_id=processor_id,
        )

        check_results = run_checks_for_processor(
            processor,
            shipments_for_processor,
            outputs,
            energy_monthly,
            certificates,
            duplicate_keys,
            as_of_month,
        )
        if site_rows:
            check_results = [*check_results, site_assessment_to_check_result(site_rows[0])]

        bq.delete_check_results_by_processor(bq_client, seed, facts_source, processor_id)
        bq.load_rows(
            bq_client,
            "check_results",
            [
                {
                    "seed": seed,
                    "facts_source": facts_source,
                    "processor_id": processor_id,
                    **r.model_dump(),
                }
                for r in check_results
            ],
        )
        checks_only_score = score_processor(
            processor,
            certificates,
            shipments_for_processor,
            duplicate_keys,
            check_results,
            as_of_month,
        )
        bq.delete_assessments_by_processor_and_stage(
            bq_client, seed, facts_source, processor_id, "checks_only"
        )
        bq.load_rows(
            bq_client,
            "assessments",
            [
                {
                    "seed": seed,
                    "facts_source": facts_source,
                    "stage": "checks_only",
                    "processor_id": processor_id,
                    "computed_at": datetime.now(UTC).isoformat(),
                    **checks_only_score,
                }
            ],
        )
        ctx.finish_stage("checking")

        # --- 3. reasoning ---
        ctx.start_stage("reasoning")
        processor_context = {
            "processor": processor,
            "certificates": certificates,
            "shipments": shipments_for_processor,
            "duplicate_keys": duplicate_keys,
            "as_of_month": as_of_month,
            "check_results": [r.model_dump() for r in check_results],
            "site_assessment": site_rows[0] if site_rows else None,
            "documents": [{**d, "fields": facts.get(d["doc_id"], {})} for d in documents_rows],
            "gcs_client": gcs_client,
        }
        loop_result, attempts = run_agent_loop_with_retry(
            processor_context, llm_client, params.AGENT_TIMEOUT_S, on_step=on_step
        )

        bq.delete_agent_runs_by_processor(bq_client, seed, facts_source, processor_id)
        agent_run_rows = []
        computed_at = datetime.now(UTC).isoformat()
        for attempt in attempts:
            for step in attempt["trail"]:
                agent_run_rows.append(
                    {
                        "seed": seed,
                        "facts_source": facts_source,
                        "processor_id": processor_id,
                        "attempt": attempt["attempt"],
                        "computed_at": computed_at,
                        "step_index": step["step_index"],
                        "step_type": step["step_type"],
                        "tool_name": step["tool_name"],
                        "tool_args_json": step["tool_args_json"],
                        "input_summary": step["input_summary"],
                        "output_json": step["output_json"],
                        "latency_ms": step.get("latency_ms"),
                        "input_tokens": step.get("input_tokens"),
                        "output_tokens": step.get("output_tokens"),
                        "thinking_tokens": step.get("thinking_tokens"),
                    }
                )
        bq.load_rows(bq_client, "agent_runs", agent_run_rows)

        score_check_results = list(check_results)
        if loop_result["systemic_findings"]:
            score_check_results.append(
                build_systemic_finding_check_result(loop_result["systemic_findings"])
            )
        if loop_result["no_evidence_findings"]:
            score_check_results.append(
                build_no_own_evidence_finding_check_result(loop_result["no_evidence_findings"])
            )
        if loop_result["review_flag_findings"]:
            score_check_results.append(
                build_disputed_finding_check_result(loop_result["review_flag_findings"])
            )
        full_score = score_processor(
            processor,
            certificates,
            shipments_for_processor,
            duplicate_keys,
            score_check_results,
            as_of_month,
            excluded_shipment_ids=loop_result["excluded_shipment_ids"],
        )
        bq.delete_assessments_by_processor_and_stage(
            bq_client, seed, facts_source, processor_id, "full"
        )
        bq.load_rows(
            bq_client,
            "assessments",
            [
                {
                    "seed": seed,
                    "facts_source": facts_source,
                    "stage": "full",
                    "processor_id": processor_id,
                    "computed_at": computed_at,
                    "agent_status": loop_result["agent_status"],
                    **full_score,
                }
            ],
        )

        findings_after = _classified_findings(loop_result)
        alert = _decide_alert(snapshot_before, full_score["risk_band"], findings_after)
        alert_id = None
        if alert is not None:
            alert_id = f"ALERT-{run_id}"
            bq.delete_by_run_id(bq_client, "alerts", run_id)
            bq.load_rows(
                bq_client,
                "alerts",
                [
                    {
                        "alert_id": alert_id,
                        "run_id": run_id,
                        "processor_id": processor_id,
                        "seed": seed,
                        "facts_source": facts_source,
                        "created_at": datetime.now(UTC).isoformat(),
                        **alert,
                    }
                ],
            )
        ctx.publish_alert_id(alert_id)
        ctx.finish_stage("reasoning")

        # --- 4. drafting_memo (English only on the live path) ---
        ctx.start_stage("drafting_memo")
        memo_context = memo.build_memo_context(
            processor=processor,
            assessment=full_score,
            check_results=[r.model_dump() for r in score_check_results],
            findings=findings_after,
            shipments_by_id={s["shipment_id"]: s for s in shipments_for_processor},
            documents_by_id={d["doc_id"]: d for d in documents_rows},
            certificates=certificates,
            as_of_month=as_of_month,
        )
        if memo_context["doc_type"] == "clarification_memo":
            english_doc, guard_status = memo.generate_clarification_memo(memo_context, llm_client)
        else:
            english_doc, guard_status = memo.generate_verification_statement(
                memo_context, llm_client
            )
        bq.delete_memos_by_processor(bq_client, seed, facts_source, processor_id)
        bq.load_rows(
            bq_client,
            "memos",
            [
                {
                    "seed": seed,
                    "facts_source": facts_source,
                    "processor_id": processor_id,
                    "doc_type": memo_context["doc_type"],
                    "lang": "en",
                    "memo_json": english_doc.model_dump_json(),
                    "guard_status": guard_status,
                    "model": settings.gemini_model,
                    "input_tokens": None,
                    "output_tokens": None,
                    "generated_at": datetime.now(UTC).isoformat(),
                }
            ],
        )
        ctx.finish_stage("drafting_memo")

        call_log = [{"seed": seed, **record} for record in llm_client.flush_call_log()]
        bq.load_rows(bq_client, "llm_calls", call_log)

        # --- 5. cache invalidate + synchronous re-warm, then done ---
        cache.invalidate(None)
        cache.preload(seed, facts_source)
        ctx.finish("done", alert_id=alert_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_certificate_batch failed for run_id=%s", run_id)
        ctx.finish("failed", error_message=str(exc))
    finally:
        with _active_runs_lock:
            _active_runs.pop(run_id, None)
