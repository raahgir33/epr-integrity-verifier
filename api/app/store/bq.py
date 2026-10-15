"""BigQuery client, table schemas, and load-job helpers.

Load jobs and DML only — never streaming inserts: rows in the streaming
buffer can't be updated or deleted for a while, which would break
idempotent re-runs. Every write in this project goes through load_rows()
(load_table_from_json) or delete_by_seed() (DML).

Only the tables T5 itself needs are defined here (processors, suppliers,
brands, documents, certificates). Later tasks add their own tables to this
same registry as the code that populates them is built.
"""

import threading

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
        # For C3a/C3b (transport checks) — UTC per internal engineering notes §6. Nullable:
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
    #
    # attempt (nullable INTEGER, added 2026-10-08 for the processor-level
    # retry — app/agents/orchestrator.py's run_agent_loop_with_retry):
    # 1 for the first attempt's steps, 2 for a retry's, if one ran. NEW
    # COLUMN on an existing table — create_tables.py's CREATE TABLE IF NOT
    # EXISTS does nothing for it; the developer needs:
    #   ALTER TABLE `epr.agent_runs` ADD COLUMN IF NOT EXISTS attempt INTEGER;
    # Existing rows get NULL until the next --stage agents / probe run
    # rewrites them (app/store/cache.py's get_agent_trail treats a NULL
    # attempt as 1, so old rows still read correctly meanwhile).
    "agent_runs": [
        bigquery.SchemaField("seed", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("facts_source", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("processor_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("attempt", "INTEGER"),
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
    # Clarification memo / verification statement feature
    # (app/agents/memo.py). Keyed one level finer than shipments/
    # check_results/agent_runs — (seed, facts_source, processor_id) via
    # delete_memos_by_processor — because scripts/run_pipeline.py's
    # --stage memo --processor PID must regenerate only that processor's
    # row(s) without wiping every other processor's memo for this (seed,
    # facts_source), unlike run_agents()'s existing delete_by_seed_and_
    # source call (which wipes the whole scope regardless of --processor
    # — a real gap noted during this feature's planning, deliberately
    # not copied here). doc_type: "clarification_memo" |
    # "verification_statement" (app/agents/memo.py's DocType). lang:
    # "en" | "hi" — a Hindi row only exists when generate_hindi_memo
    # succeeded; "en" always exists for a processor that's been through
    # --stage memo. memo_json is ClarificationMemo/VerificationStatement's
    # model_dump_json() — the API re-validates it into whichever schema
    # doc_type names (app/main.py).
    "memos": [
        bigquery.SchemaField("seed", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("facts_source", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("processor_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("doc_type", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("lang", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("memo_json", "STRING"),
        bigquery.SchemaField("guard_status", "STRING"),
        bigquery.SchemaField("model", "STRING"),
        bigquery.SchemaField("input_tokens", "INTEGER"),
        bigquery.SchemaField("output_tokens", "INTEGER"),
        bigquery.SchemaField("generated_at", "TIMESTAMP"),
    ],
    # T13 (live event path). The committed data/synthetic/seed-<seed>/
    # demo_batches.json's own rows, loaded once (scripts/
    # load_demo_extra_docs.py) — a BigQuery table, not a local file read,
    # because api/Dockerfile only COPYs app/ into the deployed image
    # (neither scripts/ nor data/ ship), so the live event path (which
    # runs inside that deployed container) can't read the JSON file off
    # local disk the way the generator/loader scripts do. Whole-seed
    # replaceable (delete_by_seed then load) — small, not facts_source-
    # dimensioned (a demo batch's own documents are extracted_facts-
    # independent until the live run itself extracts them).
    "demo_batches": [
        bigquery.SchemaField("seed", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("batch_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("processor_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("period_month", "STRING"),
        bigquery.SchemaField("quantity_t", "FLOAT"),
        bigquery.SchemaField("pushes_over_verifiable", "BOOLEAN"),
        bigquery.SchemaField("pre_batch_certified_t", "FLOAT"),
        bigquery.SchemaField("pre_batch_true_verifiable_t", "FLOAT"),
        bigquery.SchemaField("extra_document_ids", "STRING", mode="REPEATED"),
    ],
    # T13 (live event path). One row per demo click, rewritten in place
    # (delete_by_run_id then load — app/events/run_processor.py) at each
    # coarse stage transition: status moves
    # queued -> reading_documents -> checking -> reasoning -> drafting_memo
    # -> done|failed. stage_timestamps_json is a JSON object keyed by
    # completed stage name, each value {"at": ISO8601, "duration_s": float}
    # — the measured wall-clock time that stage took, which the web
    # progress view displays (e.g. "Agents reviewing - 74s"). snapshot_
    # before_json is captured once, at POST /demo/certificate-batch time,
    # from that processor's then-current "full" assessment + findings —
    # the fixed baseline the alert decision (step 4 of run_processor.py)
    # compares the post-run state against, immune to any race with the
    # write itself. alert_id is set once an alerts row is written for this
    # run, null otherwise (including every run that didn't alert).
    "runs": [
        bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("batch_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("processor_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("seed", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("facts_source", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("status", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("updated_at", "TIMESTAMP"),
        bigquery.SchemaField("stage_timestamps_json", "STRING"),
        bigquery.SchemaField("error_message", "STRING"),
        bigquery.SchemaField("snapshot_before_json", "STRING"),
        bigquery.SchemaField("alert_id", "STRING"),
    ],
    # T13 (live event path). One row per fired alert (not every run alerts
    # — only one whose risk band rose or that surfaced a new non-
    # concurs-with-check/non-withdrawn finding versus its run's own
    # snapshot_before_json). Keyed by run_id (delete_by_run_id), same as
    # "runs" — a re-delivered push for an already-alerted run must never
    # produce a second alert row for that run.
    "alerts": [
        bigquery.SchemaField("alert_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("processor_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("seed", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("facts_source", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("risk_band_before", "STRING"),
        bigquery.SchemaField("risk_band_after", "STRING"),
        bigquery.SchemaField("new_finding_summary", "STRING"),
        bigquery.SchemaField("message", "STRING"),
    ],
    # T13.6: a small, developer-written table of precomputed evaluation
    # metrics — today just the T6 full-extraction-run's key-field read
    # accuracy for GET /stats's field_read_accuracy_pct, since T14's real
    # /evaluation endpoint doesn't exist yet and ground_truth.json (what
    # the number is measured against) never ships to the deployed
    # container. Not seed/facts_source-scoped — dataset_label already
    # encodes that ("dev-seed42"; a future "heldout-seed7" row is the same
    # shape once T14 lands). Written only by
    # scripts/report_extraction_mismatches.py's --write-bq flag, one row
    # per (dataset_label, metric) — see delete_eval_metrics below for the
    # idempotency key.
    "eval_metrics": [
        bigquery.SchemaField("dataset_label", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("metric", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("numerator", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("denominator", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("computed_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("source_script", "STRING"),
        bigquery.SchemaField("git_commit", "STRING"),
    ],
}


_client: bigquery.Client | None = None
_client_lock = threading.Lock()


def fetch_rows(
    client: bigquery.Client,
    table_name: str,
    columns: str,
    seed: int,
    processor_id: str | None = None,
    facts_source: str | None = None,
) -> list[dict]:
    """General-purpose read, mirroring scripts/run_pipeline.py's own
    private _fetch_bq_rows — exposed here (not there) because T13's live
    event path (app/events/run_processor.py) runs inside the deployed
    api/ image, which never includes scripts/ (api/Dockerfile only
    `COPY app ./app` — scripts/ isn't in the deployed container), so it
    can't import anything from scripts/run_pipeline.py. Both call sites
    conceptually share this shape now; scripts/run_pipeline.py's own
    _fetch_bq_rows is left as-is (not worth the risk of touching an
    already-stable, heavily tested script for a non-functional dedup)."""
    table_ref = _table_ref(table_name)
    query = f"SELECT {columns} FROM `{table_ref}` WHERE seed = @seed"
    params = [bigquery.ScalarQueryParameter("seed", "INTEGER", seed)]
    if processor_id:
        query += " AND processor_id = @processor_id"
        params.append(bigquery.ScalarQueryParameter("processor_id", "STRING", processor_id))
    if facts_source:
        query += " AND facts_source = @facts_source"
        params.append(bigquery.ScalarQueryParameter("facts_source", "STRING", facts_source))
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    job = client.query(query, job_config=job_config, location=settings.vertex_location)
    return [dict(row) for row in job.result()]


def get_client() -> bigquery.Client:
    """Memoized: constructing bigquery.Client involves credential
    discovery and isn't free (A2's measured cold-path latency includes
    this), and the client is documented as safe to reuse across calls —
    one per process, not one per query. Lock-protected since FastAPI's
    sync `def` routes run in a thread pool; worst case on a race is two
    clients briefly constructed, never a correctness issue."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = bigquery.Client(project=settings.gcp_project)
    return _client


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


def delete_memos_by_processor(
    client: bigquery.Client, seed: int, facts_source: str, processor_id: str
) -> None:
    """memos' idempotency key is one level finer than delete_by_seed_and_
    source (seed+facts_source+processor_id, not just seed+facts_source) —
    see the "memos" schema comment above for why: a --stage memo
    --processor PID rerun must only ever touch that one processor's
    row(s) (en + an optional hi), never every processor's."""
    table_ref = _table_ref("memos")
    query = (
        f"DELETE FROM `{table_ref}` "
        "WHERE seed = @seed AND facts_source = @facts_source AND processor_id = @processor_id"
    )
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("seed", "INTEGER", seed),
            bigquery.ScalarQueryParameter("facts_source", "STRING", facts_source),
            bigquery.ScalarQueryParameter("processor_id", "STRING", processor_id),
        ]
    )
    job = client.query(query, job_config=job_config, location=settings.vertex_location)
    job.result()


def fetch_eval_metrics(client: bigquery.Client, dataset_label: str, metric: str) -> list[dict]:
    """eval_metrics isn't seed-scoped (dataset_label already encodes it),
    so it can't go through fetch_rows' seed-filtered query — same shape,
    one extra key column, ordered newest first so the caller can just take
    row 0 as "the latest" per (dataset_label, metric)."""
    table_ref = _table_ref("eval_metrics")
    query = (
        f"SELECT * FROM `{table_ref}` "
        "WHERE dataset_label = @dataset_label AND metric = @metric "
        "ORDER BY computed_at DESC"
    )
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("dataset_label", "STRING", dataset_label),
            bigquery.ScalarQueryParameter("metric", "STRING", metric),
        ]
    )
    job = client.query(query, job_config=job_config, location=settings.vertex_location)
    return [dict(row) for row in job.result()]


def fetch_eval_metrics_for_label(client: bigquery.Client, dataset_label: str) -> list[dict]:
    """Every metric row for one dataset_label (T14's GET /evaluation reads
    "heldout-seed7" and "dev-seed<N>" this way) — unlike fetch_eval_metrics
    above, this doesn't need the caller to know every metric name in
    advance, so scripts/evaluate.py can add or rename metrics without a
    matching change here. ORDER BY metric for a stable, readable listing."""
    table_ref = _table_ref("eval_metrics")
    query = f"SELECT * FROM `{table_ref}` WHERE dataset_label = @dataset_label ORDER BY metric"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("dataset_label", "STRING", dataset_label)]
    )
    job = client.query(query, job_config=job_config, location=settings.vertex_location)
    return [dict(row) for row in job.result()]


def delete_eval_metrics(client: bigquery.Client, dataset_label: str, metric: str) -> None:
    """eval_metrics' idempotency key is (dataset_label, metric) — same
    two-key-column shape as delete_memos_by_processor — so a rerun of
    scripts/report_extraction_mismatches.py --write-bq replaces that one
    row instead of accumulating duplicates."""
    table_ref = _table_ref("eval_metrics")
    query = f"DELETE FROM `{table_ref}` WHERE dataset_label = @dataset_label AND metric = @metric"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("dataset_label", "STRING", dataset_label),
            bigquery.ScalarQueryParameter("metric", "STRING", metric),
        ]
    )
    job = client.query(query, job_config=job_config, location=settings.vertex_location)
    job.result()


def delete_by_run_id(client: bigquery.Client, table_name: str, run_id: str) -> None:
    """For "runs" (rewritten at each stage transition) and "alerts" (at
    most one row per run_id) — both keyed by run_id, so a re-delivered
    push for a run already written never produces a second row for
    either table (app/events/run_processor.py)."""
    table_ref = _table_ref(table_name)
    query = f"DELETE FROM `{table_ref}` WHERE run_id = @run_id"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("run_id", "STRING", run_id)]
    )
    job = client.query(query, job_config=job_config, location=settings.vertex_location)
    job.result()


def _delete_by_processor(
    client: bigquery.Client, table_name: str, seed: int, facts_source: str, processor_id: str
) -> None:
    """Shared body for the per-processor delete helpers below — same
    granularity as delete_memos_by_processor, generalised to check_results
    and agent_runs so T13's live path can rewrite one processor's rows
    without wiping the other 9's (unlike run_checks()/run_agents()'s
    existing whole-(seed, facts_source) delete_by_seed_and_source)."""
    table_ref = _table_ref(table_name)
    query = (
        f"DELETE FROM `{table_ref}` "
        "WHERE seed = @seed AND facts_source = @facts_source AND processor_id = @processor_id"
    )
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("seed", "INTEGER", seed),
            bigquery.ScalarQueryParameter("facts_source", "STRING", facts_source),
            bigquery.ScalarQueryParameter("processor_id", "STRING", processor_id),
        ]
    )
    job = client.query(query, job_config=job_config, location=settings.vertex_location)
    job.result()


def delete_shipments_by_processor(
    client: bigquery.Client, seed: int, facts_source: str, processor_id: str
) -> None:
    _delete_by_processor(client, "shipments", seed, facts_source, processor_id)


def delete_check_results_by_processor(
    client: bigquery.Client, seed: int, facts_source: str, processor_id: str
) -> None:
    _delete_by_processor(client, "check_results", seed, facts_source, processor_id)


def delete_agent_runs_by_processor(
    client: bigquery.Client, seed: int, facts_source: str, processor_id: str
) -> None:
    _delete_by_processor(client, "agent_runs", seed, facts_source, processor_id)


def delete_assessments_by_processor_and_stage(
    client: bigquery.Client, seed: int, facts_source: str, processor_id: str, stage: str
) -> None:
    """One level finer than delete_assessments_by_stage (which deletes
    every processor's row for that stage) — T13's live path must only
    ever touch the one processor a demo batch targets."""
    table_ref = _table_ref("assessments")
    query = (
        f"DELETE FROM `{table_ref}` "
        "WHERE seed = @seed AND facts_source = @facts_source "
        "AND processor_id = @processor_id AND stage = @stage"
    )
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("seed", "INTEGER", seed),
            bigquery.ScalarQueryParameter("facts_source", "STRING", facts_source),
            bigquery.ScalarQueryParameter("processor_id", "STRING", processor_id),
            bigquery.ScalarQueryParameter("stage", "STRING", stage),
        ]
    )
    job = client.query(query, job_config=job_config, location=settings.vertex_location)
    job.result()


def delete_shipments_by_document_ids(
    client: bigquery.Client, seed: int, doc_ids: list[str]
) -> None:
    """Deletes the shipments built from any of `doc_ids` — matched on all
    three document columns, since a shipment can reference a demo
    document in any of the three roles (and may have matched only some of
    them). Used by app/admin/reset_demo.py to clear the shipment a demo
    run created: that row survives the reset otherwise, because reset
    restores assessments/check_results from a snapshot but never rewrites
    the shipments table, leaving a shipment whose certificate has been
    deleted — a month showing verified inbound tonnes against zero
    certified. Scoped by seed and to these doc_ids only, so it can never
    touch a dossier shipment. A no-op (no query) if doc_ids is empty."""
    if not doc_ids:
        return
    table_ref = _table_ref("shipments")
    query = (
        f"DELETE FROM `{table_ref}` WHERE seed = @seed AND ("
        "invoice_doc_id IN UNNEST(@doc_ids) "
        "OR eway_doc_id IN UNNEST(@doc_ids) "
        "OR weighbridge_doc_id IN UNNEST(@doc_ids))"
    )
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("seed", "INTEGER", seed),
            bigquery.ArrayQueryParameter("doc_ids", "STRING", doc_ids),
        ]
    )
    job = client.query(query, job_config=job_config, location=settings.vertex_location)
    job.result()


def delete_by_ids(client: bigquery.Client, table_name: str, id_column: str, ids: list[str]) -> None:
    """Deletes rows matching any of the given ids, regardless of seed/
    facts_source — used by scripts/reset_demo.py to remove the handful of
    doc_id/certificate_id rows a demo run touched (documents.doc_id,
    extracted_facts.doc_id, extraction_results.doc_id,
    certificates.certificate_id), where the id itself is already globally
    unique and clearly tagged (e.g. "PWP-03-DEMO-...", "CERT-DEMO-...") so
    there's no risk of matching an unrelated row. A no-op (no query) if
    ids is empty."""
    if not ids:
        return
    table_ref = _table_ref(table_name)
    query = f"DELETE FROM `{table_ref}` WHERE {id_column} IN UNNEST(@ids)"
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ArrayQueryParameter("ids", "STRING", ids)]
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
