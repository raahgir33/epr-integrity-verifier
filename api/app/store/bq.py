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
