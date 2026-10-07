"""BigQuery client, table schemas, and load-job helpers.

Load jobs and DML only — never streaming inserts: rows in the streaming
buffer can't be updated or deleted for a while, which would break
idempotent re-runs. Every write in this project goes through load_rows()
(load_table_from_json) or delete_by_seed() (DML).

Only the tables T5 itself needs are defined here (processors, suppliers,
brands, documents, certificates). Later tasks add their own tables to this
same registry as the code that populates them is built.
"""

from google.cloud import bigquery

from app.config import settings

SCHEMAS: dict[str, list[bigquery.SchemaField]] = {
    "processors": [
        bigquery.SchemaField("seed", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("processor_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING"),
        bigquery.SchemaField("type", "STRING"),
        bigquery.SchemaField("permitted_categories", "STRING", mode="REPEATED"),
        bigquery.SchemaField("capacity_t_per_year", "FLOAT"),
        bigquery.SchemaField("consent_no", "STRING"),
        bigquery.SchemaField("consent_valid_from", "DATE"),
        bigquery.SchemaField("consent_valid_to", "DATE"),
        bigquery.SchemaField("registration_no", "STRING"),
        bigquery.SchemaField("gstin", "STRING"),
        bigquery.SchemaField("address", "STRING"),
        bigquery.SchemaField("lat", "FLOAT"),
        bigquery.SchemaField("lon", "FLOAT"),
        bigquery.SchemaField("site_validated", "BOOLEAN"),
        bigquery.SchemaField("issue_types", "STRING", mode="REPEATED"),
        bigquery.SchemaField("hard_negatives", "STRING", mode="REPEATED"),
    ],
    "suppliers": [
        bigquery.SchemaField("seed", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("supplier_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING"),
        bigquery.SchemaField("gstin", "STRING"),
        bigquery.SchemaField("pin_code", "STRING"),
        bigquery.SchemaField("lat", "FLOAT"),
        bigquery.SchemaField("lon", "FLOAT"),
    ],
    "brands": [
        bigquery.SchemaField("seed", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("brand_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING"),
    ],
    "documents": [
        bigquery.SchemaField("seed", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("doc_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("processor_id", "STRING"),
        bigquery.SchemaField("doc_type", "STRING"),
        bigquery.SchemaField("lang", "STRING"),
        bigquery.SchemaField("gcs_path", "STRING"),
        bigquery.SchemaField("mime_type", "STRING"),
    ],
    "certificates": [
        bigquery.SchemaField("seed", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("certificate_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("processor_id", "STRING"),
        bigquery.SchemaField("brand_id", "STRING"),
        bigquery.SchemaField("category", "STRING"),
        bigquery.SchemaField("quantity_t", "FLOAT"),
        bigquery.SchemaField("generation_date", "DATE"),
        bigquery.SchemaField("period_month", "STRING"),
    ],
    # T6 (extraction) tables below. extracted_facts/extraction_results use
    # the same delete-by-seed-then-load idempotency as the tables above.
    # llm_calls is an append-only operational log (see load_rows callers in
    # scripts/run_pipeline.py) — re-running extraction adds to call history
    # rather than replacing it, so it's never passed to delete_by_seed.
    "extracted_facts": [
        bigquery.SchemaField("seed", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("doc_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("processor_id", "STRING"),
        bigquery.SchemaField("doc_type", "STRING"),
        bigquery.SchemaField("field_name", "STRING"),
        bigquery.SchemaField("printed_value", "STRING"),
        bigquery.SchemaField("confidence", "FLOAT"),
        bigquery.SchemaField("page", "INTEGER"),
    ],
    "extraction_results": [
        bigquery.SchemaField("seed", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("doc_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("processor_id", "STRING"),
        bigquery.SchemaField("doc_type", "STRING"),
        bigquery.SchemaField("status", "STRING"),
        bigquery.SchemaField("error_message", "STRING"),
    ],
    "llm_calls": [
        bigquery.SchemaField("seed", "INTEGER"),
        bigquery.SchemaField("purpose", "STRING"),
        bigquery.SchemaField("model", "STRING"),
        bigquery.SchemaField("latency_ms", "FLOAT"),
        bigquery.SchemaField("success", "BOOLEAN"),
        bigquery.SchemaField("called_at", "TIMESTAMP"),
        # Token usage, from the response's usage_metadata. Nullable: calls
        # made before this column existed, and failed calls, have no usage
        # data. thinking_tokens is billed as output (see scripts/cost_report.py).
        bigquery.SchemaField("input_tokens", "INTEGER"),
        bigquery.SchemaField("output_tokens", "INTEGER"),
        bigquery.SchemaField("thinking_tokens", "INTEGER"),
        bigquery.SchemaField("total_tokens", "INTEGER"),
    ],
    # T7 (normalise) tables below. Populated from either ground-truth facts
    # or real extracted_facts (docs/DATA_SPEC.md §4's matching rules) — the
    # facts_source column distinguishes the two, and idempotent re-runs
    # delete by (seed, facts_source) via delete_by_seed_and_source, so
    # loading one mode never wipes the other. No is_f8/verified columns:
    # those are ground-truth-only evaluation knowledge (stay in
    # ground_truth.json for T14), not derivable from extracted documents.
    # match_status/duplicate detection (C5) works by grouping ewb_no /
    # weighbridge_doc_id across the table itself, not a precomputed flag.
    "shipments": [
        bigquery.SchemaField("seed", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("facts_source", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("shipment_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("processor_id", "STRING"),
        bigquery.SchemaField("month", "STRING"),
        bigquery.SchemaField("invoice_doc_id", "STRING"),
        bigquery.SchemaField("eway_doc_id", "STRING"),
        bigquery.SchemaField("weighbridge_doc_id", "STRING"),
        bigquery.SchemaField("invoice_qty_t", "FLOAT"),
        bigquery.SchemaField("weighbridge_net_t", "FLOAT"),
        bigquery.SchemaField("match_status", "STRING"),
        bigquery.SchemaField("ewb_no", "STRING"),
        bigquery.SchemaField("vehicle_no", "STRING"),
        bigquery.SchemaField("distance_km", "FLOAT"),
        # For C3a/C3b (transport checks) — UTC per CLAUDE.md §6. Nullable:
        # unmatched shipments have no weighbridge_in_time, and a shipment
        # with no eway_doc_id has neither eway timestamp.
        bigquery.SchemaField("eway_generated_at", "TIMESTAMP"),
        bigquery.SchemaField("eway_valid_until", "TIMESTAMP"),
        bigquery.SchemaField("weighbridge_in_time", "TIMESTAMP"),
        # Document-content C5 duplicate keys (not internal doc IDs — see
        # checks/duplicates.py): invoice_no + supplier_gstin pair, and the
        # weighbridge ticket number. weighbridge_doc_id/invoice_doc_id are
        # internal IDs, never used as dedup keys.
        bigquery.SchemaField("invoice_no", "STRING"),
        bigquery.SchemaField("supplier_gstin", "STRING"),
        bigquery.SchemaField("weighbridge_ticket_no", "STRING"),
    ],
    "outputs": [
        bigquery.SchemaField("seed", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("facts_source", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("doc_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("processor_id", "STRING"),
        bigquery.SchemaField("month", "STRING"),
        bigquery.SchemaField("quantity_t", "FLOAT"),
    ],
    "energy_monthly": [
        bigquery.SchemaField("seed", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("facts_source", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("doc_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("processor_id", "STRING"),
        bigquery.SchemaField("month", "STRING"),
        bigquery.SchemaField("kwh", "FLOAT"),
    ],
    # T8 (checks) tables below. check_results is facts_source-dimensioned
    # like shipments/outputs/energy_monthly (delete_by_seed_and_source).
    # assessments additionally carries a stage column: "checks_only" now
    # (T8), "full" once T10's agent findings feed in — idempotent delete
    # is by (seed, facts_source, stage) via delete_assessments_by_stage,
    # so a T10 "full" run never wipes T8's "checks_only" row or vice versa.
    "check_results": [
        bigquery.SchemaField("seed", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("facts_source", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("processor_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("check_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("status", "STRING"),
        bigquery.SchemaField("severity", "STRING"),
        bigquery.SchemaField("measured", "FLOAT"),
        bigquery.SchemaField("threshold", "FLOAT"),
        bigquery.SchemaField("affected_tonnes", "FLOAT"),
        bigquery.SchemaField("evidence_ids", "STRING", mode="REPEATED"),
        bigquery.SchemaField("explanation", "STRING"),
    ],
    "assessments": [
        bigquery.SchemaField("seed", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("facts_source", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("stage", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("processor_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("certified_t", "FLOAT"),
        bigquery.SchemaField("verified_inbound_t", "FLOAT"),
        bigquery.SchemaField("capacity_limit_t", "FLOAT"),
        bigquery.SchemaField("verifiable_t", "FLOAT"),
        bigquery.SchemaField("unverifiable_t", "FLOAT"),
        bigquery.SchemaField("risk_band", "STRING"),
        # T10: how the "full" stage's agent loop finished for this
        # processor — "ok", "timeout" or "error". Null for "checks_only"
        # rows, which never run the agent loop. On timeout/error the row's
        # tonnage/risk_band columns above are the checks_only fallback
        # values (app/agents/orchestrator.py), never a partial guess.
        bigquery.SchemaField("agent_status", "STRING"),
        bigquery.SchemaField("computed_at", "TIMESTAMP"),
    ],
    # T9 (site check C8). Not facts_source-dimensioned — C8 depends only
    # on a processor's registered coordinates (seed-level), never on
    # extracted documents, so delete_by_seed is the right idempotency
    # key (like documents/certificates, not shipments/check_results).
    # polygons_json is evidence/count data (confidence + area + exterior
    # ring per building), not used for client-side drawing — the overlay
    # is painted server-side onto the thumbnail itself (geo/site.py).
    "site_assessments": [
        bigquery.SchemaField("seed", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("processor_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("status", "STRING"),
        bigquery.SchemaField("severity", "STRING"),
        bigquery.SchemaField("measured", "FLOAT"),
        bigquery.SchemaField("threshold", "FLOAT"),
        bigquery.SchemaField("building_count", "INTEGER"),
        bigquery.SchemaField("total_footprint_m2", "FLOAT"),
        bigquery.SchemaField("polygons_json", "STRING"),
        bigquery.SchemaField("thumbnail_gcs_path", "STRING"),
        bigquery.SchemaField("thumb_bbox_w", "FLOAT"),
        bigquery.SchemaField("thumb_bbox_s", "FLOAT"),
        bigquery.SchemaField("thumb_bbox_e", "FLOAT"),
        bigquery.SchemaField("thumb_bbox_n", "FLOAT"),
        bigquery.SchemaField("thumb_crs", "STRING"),
        bigquery.SchemaField("explanation", "STRING"),
        bigquery.SchemaField("computed_at", "TIMESTAMP"),
    ],
    # T10 (agent loop). One row per step in orchestrator.py's trail
    # (Hypothesis, each tool call, the Critic's final structured call,
    # revision). facts_source-dimensioned like shipments/check_results —
    # delete_by_seed_and_source is this table's idempotency key, same
    # pattern, not a new one. tool_name/tool_args_json are null for a
    # non-tool step.
    "agent_runs": [
        bigquery.SchemaField("seed", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("facts_source", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("processor_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("step_index", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("step_type", "STRING"),
        bigquery.SchemaField("tool_name", "STRING"),
        bigquery.SchemaField("tool_args_json", "STRING"),
        bigquery.SchemaField("input_summary", "STRING"),
        bigquery.SchemaField("output_json", "STRING"),
        bigquery.SchemaField("latency_ms", "FLOAT"),
        bigquery.SchemaField("input_tokens", "INTEGER"),
        bigquery.SchemaField("output_tokens", "INTEGER"),
        bigquery.SchemaField("thinking_tokens", "INTEGER"),
        bigquery.SchemaField("computed_at", "TIMESTAMP"),
    ],
}


def get_client() -> bigquery.Client:
    return bigquery.Client(project=settings.gcp_project)


def _table_ref(table_name: str) -> str:
    return f"{settings.gcp_project}.{settings.bq_dataset}.{table_name}"


def create_tables(client: bigquery.Client) -> None:
    for table_name, schema in SCHEMAS.items():
        table = bigquery.Table(_table_ref(table_name), schema=schema)
        client.create_table(table, exists_ok=True)


def delete_by_seed(client: bigquery.Client, table_name: str, seed: int) -> None:
    query = f"DELETE FROM `{_table_ref(table_name)}` WHERE seed = @seed"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("seed", "INTEGER", seed)]
    )
    job = client.query(query, job_config=job_config, location=settings.vertex_location)
    job.result()


def delete_by_seed_and_source(
    client: bigquery.Client, table_name: str, seed: int, facts_source: str
) -> None:
    """For the facts_source-dimensioned tables (shipments, outputs,
    energy_monthly) — deletes only this seed+mode's rows, so loading truth
    mode never wipes extracted mode's rows or vice versa."""
    table_ref = _table_ref(table_name)
    query = f"DELETE FROM `{table_ref}` WHERE seed = @seed AND facts_source = @facts_source"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("seed", "INTEGER", seed),
            bigquery.ScalarQueryParameter("facts_source", "STRING", facts_source),
        ]
    )
    job = client.query(query, job_config=job_config, location=settings.vertex_location)
    job.result()


def delete_assessments_by_stage(
    client: bigquery.Client, seed: int, facts_source: str, stage: str
) -> None:
    """assessments is keyed one level finer than delete_by_seed_and_source:
    a T10 "full" rerun must never delete T8's "checks_only" row, or vice
    versa, for the same (seed, facts_source)."""
    table_ref = _table_ref("assessments")
    query = (
        f"DELETE FROM `{table_ref}` "
        "WHERE seed = @seed AND facts_source = @facts_source AND stage = @stage"
    )
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("seed", "INTEGER", seed),
            bigquery.ScalarQueryParameter("facts_source", "STRING", facts_source),
            bigquery.ScalarQueryParameter("stage", "STRING", stage),
        ]
    )
    job = client.query(query, job_config=job_config, location=settings.vertex_location)
    job.result()


def load_rows(client: bigquery.Client, table_name: str, rows: list[dict]) -> int:
    """Loads `rows` into `table_name` via a load job. Returns the row count."""
    if not rows:
        return 0
    job_config = bigquery.LoadJobConfig(
        schema=SCHEMAS[table_name],
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )
    job = client.load_table_from_json(
        rows, _table_ref(table_name), job_config=job_config, location=settings.vertex_location
    )
    job.result()
    if job.errors:
        raise RuntimeError(f"load job for {table_name} failed: {job.errors}")
    return len(rows)
