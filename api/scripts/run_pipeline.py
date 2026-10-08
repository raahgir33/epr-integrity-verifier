"""Precompute pipeline: extract -> normalize -> checks -> site -> agents.
All five stages are implemented. --stage agents currently only supports
--facts-source truth (see docs/PROGRESS.md's Deferred Items ledger — a
re-run against extracted facts is deferred until after the full
496-document extraction run).

Run by the developer — never by the agent (hits real Vertex AI, BigQuery,
Cloud Storage, Earth Engine).

Usage: uv run python scripts/run_pipeline.py --seed 42 --stage extract
       uv run python scripts/run_pipeline.py --seed 42 --stage extract --processor PWP-01
       uv run python scripts/run_pipeline.py --seed 42 --stage normalize --facts-source truth
       uv run python scripts/run_pipeline.py --seed 42 --stage normalize --facts-source extracted
       uv run python scripts/run_pipeline.py --seed 42 --stage checks --facts-source truth
       uv run python scripts/run_pipeline.py --seed 42 --stage site
       uv run python scripts/run_pipeline.py --seed 42 --stage agents --facts-source truth
"""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from google.cloud import bigquery

from app.agents.orchestrator import run_agent_loop
from app.agents.scorer import (
    build_disputed_finding_check_result,
    build_no_own_evidence_finding_check_result,
    build_systemic_finding_check_result,
    score_processor,
)
from app.checks import params
from app.checks.duplicates import find_duplicate_keys
from app.checks.runner import run_checks_for_processor
from app.config import settings
from app.eval.evaluate import extraction_field_accuracy
from app.geo.site import run_site_assessment, site_assessment_to_check_result, upload_thumbnail
from app.ingest.extract import extract_all, facts_to_field_rows
from app.ingest.normalize import (
    EXTRACTED,
    TRUTH,
    energy_from_extracted,
    energy_from_truth,
    facts_by_doc_id,
    match_shipments_from_extracted,
    outputs_from_extracted,
    outputs_from_truth,
    shipments_from_truth,
)
from app.llm import GeminiClient
from app.models.checks import CheckResult
from app.store import bq, gcs
from scripts.load_dossiers import document_gcs_path

REPO_ROOT = Path(__file__).resolve().parents[2]
ACCURACY_GATE = 0.90


def load_ground_truth(seed: int) -> dict:
    path = REPO_ROOT / "data" / "synthetic" / f"seed-{seed}" / "ground_truth.json"
    return json.loads(path.read_text(encoding="utf-8"))


def run_extract(seed: int, processor_filter: str | None) -> None:
    ground_truth = load_ground_truth(seed)
    documents = ground_truth["documents"]
    if processor_filter:
        documents = [d for d in documents if d["processor_id"] == processor_filter]
    if not documents:
        print(
            f"No documents found for seed {seed}"
            + (f", processor {processor_filter}" if processor_filter else "")
        )
        return

    docs_with_paths = [dict(d, gcs_path=document_gcs_path(seed, d)) for d in documents]

    print(f"Extracting {len(docs_with_paths)} documents (concurrency 4)...")
    llm_client = GeminiClient()
    gcs_client = gcs.get_client()
    results = extract_all(llm_client, gcs_client, settings.dossier_bucket, docs_with_paths)

    extracted_facts_rows = []
    extraction_results_rows = []
    ok_count = 0
    failed_count = 0
    for result in results:
        base = {
            "seed": seed,
            "doc_id": result["doc_id"],
            "processor_id": result["processor_id"],
            "doc_type": result["doc_type"],
        }
        if result["status"] == "ok":
            ok_count += 1
            for field_row in facts_to_field_rows(result["facts"]):
                extracted_facts_rows.append({**base, **field_row})
            extraction_results_rows.append({**base, "status": "ok", "error_message": None})
        else:
            failed_count += 1
            extraction_results_rows.append(
                {**base, "status": "failed", "error_message": result["error"]}
            )

    print(f"Extraction done: {ok_count} ok, {failed_count} failed.")

    bq_client = bq.get_client()
    bq.delete_by_seed(bq_client, "extracted_facts", seed)
    bq.load_rows(bq_client, "extracted_facts", extracted_facts_rows)
    bq.delete_by_seed(bq_client, "extraction_results", seed)
    bq.load_rows(bq_client, "extraction_results", extraction_results_rows)

    call_log = [{"seed": seed, **record} for record in llm_client.flush_call_log()]
    bq.load_rows(bq_client, "llm_calls", call_log)

    report = extraction_field_accuracy(extracted_facts_rows, documents)
    print("\nField accuracy by document type (key numeric/ID fields only):")
    for doc_type, stats in sorted(report.items()):
        if doc_type == "overall":
            continue
        acc = f"{stats['accuracy']:.1%}" if stats["accuracy"] is not None else "n/a"
        print(f"  {doc_type:20s} {stats['correct']:4d}/{stats['total']:<4d}  {acc}")

    overall = report["overall"]
    overall_acc = overall["accuracy"] or 0.0
    print(f"\nOverall: {overall['correct']}/{overall['total']} ({overall_acc:.1%})")
    gate_status = "PASS" if overall_acc >= ACCURACY_GATE else "FAIL"
    print(f"Gate (>= {ACCURACY_GATE:.0%}): {gate_status}")


def _fetch_bq_rows(
    client,
    table: str,
    columns: str,
    seed: int,
    processor_filter: str | None,
    facts_source: str | None = None,
) -> list[dict]:
    table_ref = f"{settings.gcp_project}.{settings.bq_dataset}.{table}"
    query = f"SELECT {columns} FROM `{table_ref}` WHERE seed = @seed"
    params = [bigquery.ScalarQueryParameter("seed", "INTEGER", seed)]
    if processor_filter:
        query += " AND processor_id = @processor_id"
        params.append(bigquery.ScalarQueryParameter("processor_id", "STRING", processor_filter))
    if facts_source:
        query += " AND facts_source = @facts_source"
        params.append(bigquery.ScalarQueryParameter("facts_source", "STRING", facts_source))
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    job = client.query(query, job_config=job_config, location=settings.vertex_location)
    return [dict(row) for row in job.result()]


def _group_by_processor(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["processor_id"], []).append(row)
    return grouped


def run_normalize(seed: int, facts_source: str, processor_filter: str | None) -> None:
    all_shipments: list[dict] = []
    all_outputs: list[dict] = []
    all_energy: list[dict] = []
    invoice_count = 0

    if facts_source == TRUTH:
        ground_truth = load_ground_truth(seed)
        processors = ground_truth["processors"]
        if processor_filter:
            processors = [p for p in processors if p["processor_id"] == processor_filter]
        for p in processors:
            pid = p["processor_id"]
            all_shipments.extend(
                shipments_from_truth(seed, pid, p["shipments"], ground_truth["documents"])
            )
            all_outputs.extend(outputs_from_truth(seed, pid, p["outputs"]))
            all_energy.extend(energy_from_truth(seed, pid, p["energy_monthly"]))
        invoice_count = sum(
            1
            for d in ground_truth["documents"]
            if d["doc_type"] == "inbound_invoice"
            and (not processor_filter or d["processor_id"] == processor_filter)
        )
    else:
        bq_client = bq.get_client()
        documents = _fetch_bq_rows(
            bq_client, "documents", "doc_id, processor_id, doc_type", seed, processor_filter
        )
        extracted_rows = _fetch_bq_rows(
            bq_client,
            "extracted_facts",
            "doc_id, processor_id, field_name, printed_value",
            seed,
            processor_filter,
        )
        docs_by_processor = _group_by_processor(documents)
        facts_by_processor = _group_by_processor(extracted_rows)
        invoice_count = sum(1 for d in documents if d["doc_type"] == "inbound_invoice")

        for pid, docs in docs_by_processor.items():
            facts = facts_by_doc_id(facts_by_processor.get(pid, []))
            all_shipments.extend(match_shipments_from_extracted(seed, pid, docs, facts))
            all_outputs.extend(outputs_from_extracted(seed, pid, docs, facts))
            all_energy.extend(energy_from_extracted(seed, pid, docs, facts))

    bq_client = bq.get_client()
    bq.delete_by_seed_and_source(bq_client, "shipments", seed, facts_source)
    bq.load_rows(bq_client, "shipments", all_shipments)
    bq.delete_by_seed_and_source(bq_client, "outputs", seed, facts_source)
    bq.load_rows(bq_client, "outputs", all_outputs)
    bq.delete_by_seed_and_source(bq_client, "energy_monthly", seed, facts_source)
    bq.load_rows(bq_client, "energy_monthly", all_energy)

    matched = sum(1 for s in all_shipments if s["match_status"] == "matched")
    unmatched = sum(1 for s in all_shipments if s["match_status"] == "unmatched")

    print(f"Normalise ({facts_source}) done:")
    print(f"  shipments: {len(all_shipments)} (matched={matched}, unmatched={unmatched})")
    print(f"  inbound invoice documents: {invoice_count}", end=" ")
    print("[OK, counts match]" if invoice_count == len(all_shipments) else "[MISMATCH]")
    print(f"  outputs: {len(all_outputs)}")
    print(f"  energy_monthly: {len(all_energy)}")


def _row_timestamp_to_iso(value) -> str | None:
    """BigQuery TIMESTAMP columns come back as timezone-aware
    datetime.datetime; checks/transport.py expects an ISO string."""
    return None if value is None else value.isoformat()


def _row_date_to_ddmmyyyy(value) -> str | None:
    """BigQuery DATE columns come back as datetime.date; checks/capacity.py
    and checks/consent.py expect the printed "DD/MM/YYYY" format, parsed
    through units.py — matching how they're built and tested against
    ground_truth.json's own printed fields."""
    return None if value is None else value.strftime("%d/%m/%Y")


def run_site(seed: int, processor_filter: str | None) -> None:
    bq_client = bq.get_client()
    gcs_client = gcs.get_client()

    processors = _fetch_bq_rows(
        bq_client,
        "processors",
        "processor_id, capacity_t_per_year, lat, lon",
        seed,
        processor_filter,
    )
    if not processors:
        print(
            f"No processors found for seed {seed}"
            + (f", processor {processor_filter}" if processor_filter else "")
        )
        return

    computed_at = datetime.now(UTC).isoformat()
    site_rows = []
    local_snapshot = []
    print(f"Running site check for {len(processors)} processor(s)...")
    for processor in processors:
        pid = processor["processor_id"]
        row, thumbnail_bytes = run_site_assessment(processor)
        thumbnail_gcs_path = upload_thumbnail(
            gcs_client, settings.artifact_bucket, seed, pid, thumbnail_bytes
        )
        full_row = {
            "seed": seed,
            "computed_at": computed_at,
            "thumbnail_gcs_path": thumbnail_gcs_path,
            **row,
        }
        site_rows.append(full_row)
        local_snapshot.append({k: v for k, v in full_row.items() if k != "seed"})
        print(
            f"  {pid}: buildings={row['building_count']} "
            f"footprint={row['total_footprint_m2']:.1f} m^2 status={row['status']} "
            f"-> {thumbnail_gcs_path}"
        )

    bq.delete_by_seed(bq_client, "site_assessments", seed)
    bq.load_rows(bq_client, "site_assessments", site_rows)

    if not processor_filter:
        snapshot_path = REPO_ROOT / "data" / "synthetic" / f"seed-{seed}" / "site_assessments.json"
        snapshot_path.write_text(json.dumps(local_snapshot, indent=2), encoding="utf-8")
        print(f"\nWrote local snapshot: {snapshot_path}")
    else:
        print(
            "\nSkipped the local snapshot (only written for a full, unfiltered run — "
            "a --processor run would otherwise overwrite it with one entry)."
        )

    print(f"\nSite check (seed {seed}) done: {len(site_rows)} processor(s).")


def run_checks(
    seed: int, facts_source: str, processor_filter: str | None, as_of_month: str | None
) -> None:
    bq_client = bq.get_client()

    processor_rows = _fetch_bq_rows(
        bq_client,
        "processors",
        "processor_id, type, capacity_t_per_year, permitted_categories, "
        "consent_valid_from, consent_valid_to",
        seed,
        processor_filter,
    )
    processors = [
        {
            **p,
            "consent_valid_from": _row_date_to_ddmmyyyy(p["consent_valid_from"]),
            "consent_valid_to": _row_date_to_ddmmyyyy(p["consent_valid_to"]),
        }
        for p in processor_rows
    ]

    certificate_rows = _fetch_bq_rows(
        bq_client,
        "certificates",
        "certificate_id, processor_id, category, quantity_t, period_month, generation_date",
        seed,
        processor_filter,
    )
    certificates = [
        {**c, "generation_date": _row_date_to_ddmmyyyy(c["generation_date"])}
        for c in certificate_rows
    ]
    certificates_by_processor = _group_by_processor(certificates)

    shipment_rows = _fetch_bq_rows(
        bq_client,
        "shipments",
        "shipment_id, processor_id, month, invoice_doc_id, eway_doc_id, weighbridge_doc_id, "
        "invoice_qty_t, weighbridge_net_t, match_status, ewb_no, vehicle_no, distance_km, "
        "eway_generated_at, eway_valid_until, weighbridge_in_time, invoice_no, supplier_gstin, "
        "weighbridge_ticket_no",
        seed,
        processor_filter,
        facts_source=facts_source,
    )
    shipments = [
        {
            **s,
            "eway_generated_at": _row_timestamp_to_iso(s["eway_generated_at"]),
            "eway_valid_until": _row_timestamp_to_iso(s["eway_valid_until"]),
            "weighbridge_in_time": _row_timestamp_to_iso(s["weighbridge_in_time"]),
        }
        for s in shipment_rows
    ]
    shipments_by_processor = _group_by_processor(shipments)

    outputs = _fetch_bq_rows(
        bq_client,
        "outputs",
        "doc_id, processor_id, month, quantity_t",
        seed,
        processor_filter,
        facts_source=facts_source,
    )
    outputs_by_processor = _group_by_processor(outputs)

    energy_monthly = _fetch_bq_rows(
        bq_client,
        "energy_monthly",
        "doc_id, processor_id, month, kwh",
        seed,
        processor_filter,
        facts_source=facts_source,
    )
    energy_by_processor = _group_by_processor(energy_monthly)

    # C8 (site) isn't facts_source-dimensioned (seed-level, not tied to
    # extracted documents) — read whatever --stage site has already
    # written. If it hasn't run yet, skip C8 for this run rather than
    # failing; the soft-signal bump just has nothing to find.
    site_rows = _fetch_bq_rows(
        bq_client,
        "site_assessments",
        "processor_id, status, severity, measured, threshold, thumbnail_gcs_path, explanation",
        seed,
        processor_filter,
    )
    site_by_processor = {row["processor_id"]: row for row in site_rows}

    if as_of_month is None:
        months = [c["period_month"] for c in certificates]
        if not months:
            print("No certificates found for this seed; cannot determine as_of_month.")
            return
        as_of_month = max(months)

    duplicate_keys = find_duplicate_keys(shipments)

    check_rows = []
    assessment_rows = []
    computed_at = datetime.now(UTC).isoformat()
    for processor in processors:
        pid = processor["processor_id"]
        p_shipments = shipments_by_processor.get(pid, [])
        p_outputs = outputs_by_processor.get(pid, [])
        p_energy = energy_by_processor.get(pid, [])
        p_certificates = certificates_by_processor.get(pid, [])

        results = run_checks_for_processor(
            processor, p_shipments, p_outputs, p_energy, p_certificates, duplicate_keys, as_of_month
        )
        site_row = site_by_processor.get(pid)
        if site_row is not None:
            results = [*results, site_assessment_to_check_result(site_row)]
        for r in results:
            check_rows.append(
                {"seed": seed, "facts_source": facts_source, "processor_id": pid, **r.model_dump()}
            )

        score = score_processor(
            processor, p_certificates, p_shipments, duplicate_keys, results, as_of_month
        )
        assessment_rows.append(
            {
                "seed": seed,
                "facts_source": facts_source,
                "stage": "checks_only",
                "computed_at": computed_at,
                **score,
            }
        )

    bq.delete_by_seed_and_source(bq_client, "check_results", seed, facts_source)
    bq.load_rows(bq_client, "check_results", check_rows)
    bq.delete_assessments_by_stage(bq_client, seed, facts_source, "checks_only")
    bq.load_rows(bq_client, "assessments", assessment_rows)

    print(f"Checks ({facts_source}) done, as_of_month={as_of_month}:")
    for row in assessment_rows:
        print(
            f"  {row['processor_id']}: certified={row['certified_t']:.2f}t "
            f"verifiable={row['verifiable_t']:.2f}t unverifiable={row['unverifiable_t']:.2f}t "
            f"risk={row['risk_band']}"
        )


def _to_gcs_uri(relative_path: str) -> str:
    """documents.gcs_path (and document_gcs_path()) store the blob path
    relative to the dossier bucket, not a gs:// URI — app/agents/tools.py's
    read_document needs the full URI to parse bucket/blob_path back apart."""
    return f"gs://{settings.dossier_bucket}/{relative_path}"


def _documents_from_truth(
    seed: int, ground_truth: dict, processor_filter: str | None
) -> list[dict]:
    """ground_truth.json's documents, printed-only field values — never
    canonical (T10's leak guard: a real extraction could never recover
    canonical; same principle as app/ingest/normalize.py's
    shipments_from_truth)."""
    documents = ground_truth["documents"]
    if processor_filter:
        documents = [d for d in documents if d["processor_id"] == processor_filter]
    return [
        {
            "doc_id": d["doc_id"],
            "processor_id": d["processor_id"],
            "doc_type": d["doc_type"],
            "lang": d.get("lang"),
            "gcs_path": _to_gcs_uri(document_gcs_path(seed, d)),
            "fields": {name: info.get("printed") for name, info in d.get("fields", {}).items()},
        }
        for d in documents
    ]


def fetch_agent_inputs(
    bq_client, seed: int, facts_source: str, processor_filter: str | None
) -> dict | None:
    """Everything --stage agents needs per processor, grouped by
    processor_id. Shared by run_agents() below and
    scripts/probe_agent_thinking.py so both build the exact same
    processor_context shape from the exact same query — no second,
    divergent copy of this fetch logic. Returns None (after printing why)
    if there's nothing to run against."""
    ground_truth = load_ground_truth(seed)

    processor_rows = _fetch_bq_rows(
        bq_client,
        "processors",
        "processor_id, capacity_t_per_year, permitted_categories, "
        "consent_valid_from, consent_valid_to",
        seed,
        processor_filter,
    )
    processors = [
        {
            **p,
            "consent_valid_from": _row_date_to_ddmmyyyy(p["consent_valid_from"]),
            "consent_valid_to": _row_date_to_ddmmyyyy(p["consent_valid_to"]),
        }
        for p in processor_rows
    ]
    if not processors:
        print(
            f"No processors found for seed {seed}"
            + (f", processor {processor_filter}" if processor_filter else "")
        )
        return None

    certificate_rows = _fetch_bq_rows(
        bq_client,
        "certificates",
        "certificate_id, processor_id, category, quantity_t, period_month, generation_date",
        seed,
        processor_filter,
    )
    certificates = [
        {**c, "generation_date": _row_date_to_ddmmyyyy(c["generation_date"])}
        for c in certificate_rows
    ]
    certificates_by_processor = _group_by_processor(certificates)

    shipment_rows = _fetch_bq_rows(
        bq_client,
        "shipments",
        "shipment_id, processor_id, month, invoice_doc_id, eway_doc_id, weighbridge_doc_id, "
        "invoice_qty_t, weighbridge_net_t, match_status, ewb_no, vehicle_no, distance_km, "
        "eway_generated_at, eway_valid_until, weighbridge_in_time, invoice_no, supplier_gstin, "
        "weighbridge_ticket_no",
        seed,
        processor_filter,
        facts_source=facts_source,
    )
    shipments = [
        {
            **s,
            "eway_generated_at": _row_timestamp_to_iso(s["eway_generated_at"]),
            "eway_valid_until": _row_timestamp_to_iso(s["eway_valid_until"]),
            "weighbridge_in_time": _row_timestamp_to_iso(s["weighbridge_in_time"]),
        }
        for s in shipment_rows
    ]
    shipments_by_processor = _group_by_processor(shipments)
    duplicate_keys = find_duplicate_keys(shipments)

    check_rows = _fetch_bq_rows(
        bq_client,
        "check_results",
        "processor_id, check_id, status, severity, measured, threshold, affected_tonnes, "
        "evidence_ids, explanation",
        seed,
        processor_filter,
        facts_source=facts_source,
    )
    checks_by_processor = _group_by_processor(check_rows)

    site_rows = _fetch_bq_rows(
        bq_client,
        "site_assessments",
        "processor_id, status, severity, measured, threshold, building_count, "
        "total_footprint_m2, thumbnail_gcs_path, explanation",
        seed,
        processor_filter,
    )
    site_by_processor = {row["processor_id"]: row for row in site_rows}

    documents_by_processor = _group_by_processor(
        _documents_from_truth(seed, ground_truth, processor_filter)
    )

    months = [c["period_month"] for c in certificates]
    if not months:
        print("No certificates found for this seed; cannot determine as_of_month.")
        return None

    return {
        "processors": processors,
        "certificates_by_processor": certificates_by_processor,
        "shipments_by_processor": shipments_by_processor,
        "duplicate_keys": duplicate_keys,
        "checks_by_processor": checks_by_processor,
        "site_by_processor": site_by_processor,
        "documents_by_processor": documents_by_processor,
        "as_of_month": max(months),
    }


def build_processor_context(inputs: dict, processor: dict, gcs_client) -> tuple[dict, list]:
    """Returns (processor_context, check_result_models) — the first for
    run_agent_loop/app/agents/tools.py (plain dicts), the second for
    app/agents/scorer.py's score_processor (CheckResult objects; only
    apply_soft_signal_bump needs attribute access)."""
    pid = processor["processor_id"]
    check_result_dicts = inputs["checks_by_processor"].get(pid, [])
    check_result_models = [
        CheckResult(**{k: v for k, v in c.items() if k != "processor_id"})
        for c in check_result_dicts
    ]
    processor_context = {
        "processor": processor,
        "certificates": inputs["certificates_by_processor"].get(pid, []),
        "shipments": inputs["shipments_by_processor"].get(pid, []),
        "duplicate_keys": inputs["duplicate_keys"],
        "as_of_month": inputs["as_of_month"],
        "check_results": check_result_dicts,
        "site_assessment": inputs["site_by_processor"].get(pid),
        "documents": inputs["documents_by_processor"].get(pid, []),
        "gcs_client": gcs_client,
    }
    return processor_context, check_result_models


def run_agents(
    seed: int, facts_source: str, processor_filter: str | None, as_of_month: str | None
) -> None:
    if facts_source != TRUTH:
        print(
            "--stage agents currently only supports --facts-source truth "
            "(see docs/PROGRESS.md's Deferred Items ledger)."
        )
        return

    bq_client = bq.get_client()
    gcs_client = gcs.get_client()
    inputs = fetch_agent_inputs(bq_client, seed, facts_source, processor_filter)
    if inputs is None:
        return
    processors = inputs["processors"]
    if as_of_month is None:
        as_of_month = inputs["as_of_month"]
    # build_processor_context reads as_of_month from inputs, not a separate
    # parameter — keep it in sync with whatever's actually being used
    # (default or --as-of-month override) so the context pack's
    # capacity_status matches the figures this run is scoring against.
    inputs["as_of_month"] = as_of_month

    llm_client = GeminiClient()
    agent_run_rows = []
    assessment_rows = []
    computed_at = datetime.now(UTC).isoformat()

    print(f"Running agent loop for {len(processors)} processor(s), as_of_month={as_of_month}...")
    for processor in processors:
        pid = processor["processor_id"]
        processor_context, p_check_results = build_processor_context(inputs, processor, gcs_client)
        p_shipments = processor_context["shipments"]
        p_certificates = processor_context["certificates"]
        duplicate_keys = processor_context["duplicate_keys"]

        deadline = time.monotonic() + params.AGENT_TIMEOUT_S
        loop_result = run_agent_loop(processor_context, llm_client, deadline)

        for step in loop_result["trail"]:
            agent_run_rows.append(
                {
                    "seed": seed,
                    "facts_source": facts_source,
                    "processor_id": pid,
                    "computed_at": computed_at,
                    "step_index": step["step_index"],
                    "step_type": step["step_type"],
                    "tool_name": step["tool_name"],
                    "tool_args_json": step["tool_args_json"],
                    "input_summary": step["input_summary"],
                    "output_json": step["output_json"],
                    # Per-step latency/token usage isn't captured here —
                    # the authoritative call-level accounting is
                    # llm_calls (flushed below), keyed by purpose, not by
                    # trail step.
                    "latency_ms": None,
                    "input_tokens": None,
                    "output_tokens": None,
                    "thinking_tokens": None,
                }
            )

        # Own-evidence rule + systemic-finding guard + Hypothesis/Critic
        # agreement rule (docs/PROGRESS.md): only deductible_findings
        # subtract shipment tonnage, and only for their own evidenced
        # shipments (loop_result["excluded_shipment_ids"] is the
        # ready-made deduction set, computed once in
        # app/agents/orchestrator.py's _classify_findings — not re-derived
        # from cited_shipment_ids here). systemic_findings,
        # no_evidence_findings and review_flag_findings are all kept
        # (visible in agent_runs/the UI) and instead ride a synthetic
        # soft-signal check result into score_processor's existing
        # one-step risk-band bump. concurs_with_check_findings is also
        # kept visible but deliberately gets no synthetic check result at
        # all — it only restates what a deterministic check already
        # flagged, so it rides that check's own scoring impact rather than
        # adding a second one.
        score_check_results = list(p_check_results)
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
        score = score_processor(
            processor,
            p_certificates,
            p_shipments,
            duplicate_keys,
            score_check_results,
            as_of_month,
            excluded_shipment_ids=loop_result["excluded_shipment_ids"],
        )
        assessment_rows.append(
            {
                "seed": seed,
                "facts_source": facts_source,
                "stage": "full",
                "computed_at": computed_at,
                "agent_status": loop_result["agent_status"],
                **score,
            }
        )
        print(
            f"  {pid}: agent_status={loop_result['agent_status']} "
            f"confirmed_findings={len(loop_result['confirmed_findings'])} "
            f"(deductible={len(loop_result['deductible_findings'])}, "
            f"systemic={len(loop_result['systemic_findings'])}, "
            f"no_evidence={len(loop_result['no_evidence_findings'])}, "
            f"concurs_with_check={len(loop_result['concurs_with_check_findings'])}, "
            f"review_flag={len(loop_result['review_flag_findings'])}, "
            f"withdrawn={len(loop_result['withdrawn_findings'])}) "
            f"verifiable={score['verifiable_t']:.2f}t unverifiable={score['unverifiable_t']:.2f}t "
            f"risk={score['risk_band']}"
        )

    bq.delete_by_seed_and_source(bq_client, "agent_runs", seed, facts_source)
    bq.load_rows(bq_client, "agent_runs", agent_run_rows)
    bq.delete_assessments_by_stage(bq_client, seed, facts_source, "full")
    bq.load_rows(bq_client, "assessments", assessment_rows)

    call_log = [{"seed": seed, **record} for record in llm_client.flush_call_log()]
    bq.load_rows(bq_client, "llm_calls", call_log)

    print(f"\nAgent loop (seed {seed}, {facts_source}) done: {len(processors)} processor(s).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run precompute pipeline stages.")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument(
        "--stage", choices=["extract", "normalize", "checks", "site", "agents"], required=True
    )
    parser.add_argument("--processor", help="Only process this processor_id (e.g. PWP-01)")
    parser.add_argument(
        "--facts-source",
        choices=[TRUTH, EXTRACTED],
        default=TRUTH,
        help="For --stage normalize/checks: build from ground truth or real extracted_facts.",
    )
    parser.add_argument(
        "--as-of-month",
        help="For --stage checks: 'YYYY-MM'. Default: the max period_month across every "
        "processor's certificates in this run (T13's live-demo batch will pass its own).",
    )
    args = parser.parse_args()

    if args.stage == "extract":
        run_extract(args.seed, args.processor)
    elif args.stage == "normalize":
        run_normalize(args.seed, args.facts_source, args.processor)
    elif args.stage == "checks":
        run_checks(args.seed, args.facts_source, args.processor, args.as_of_month)
    elif args.stage == "site":
        run_site(args.seed, args.processor)
    elif args.stage == "agents":
        run_agents(args.seed, args.facts_source, args.processor, args.as_of_month)


if __name__ == "__main__":
    main()
