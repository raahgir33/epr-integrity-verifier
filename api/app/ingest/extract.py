"""Gemini structured extraction per document type.

Concurrency 4. Each worker downloads its document from GCS
and calls the LLMClient; a schema-validation failure gets one retry, then
the document is recorded as failed and the pool moves on — never one
document's failure blocking the rest.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.ingest.schemas import SCHEMA_BY_DOC_TYPE
from app.llm import LLMClient
from app.store import gcs

logger = logging.getLogger(__name__)

CONCURRENCY = 4
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

MIME_TYPE_BY_DOC_TYPE = {
    doc_type: ("image/png" if doc_type == "weighbridge_slip" else "application/pdf")
    for doc_type in SCHEMA_BY_DOC_TYPE
}


def _load_prompts() -> dict[str, str]:
    return {
        doc_type: (_PROMPTS_DIR / f"{doc_type}.txt").read_text(encoding="utf-8")
        for doc_type in SCHEMA_BY_DOC_TYPE
    }


PROMPT_BY_DOC_TYPE = _load_prompts()


def facts_to_field_rows(facts: BaseModel) -> list[dict]:
    """Flattens an extraction schema instance into extracted_facts rows:
    one per field, joined against its self-reported confidence/page."""
    data = facts.model_dump()
    confidences = {fc["field"]: fc for fc in data.pop("field_confidence", [])}
    rows = []
    for field_name, printed_value in data.items():
        fc = confidences.get(field_name, {})
        rows.append(
            {
                "field_name": field_name,
                "printed_value": printed_value,
                "confidence": fc.get("confidence"),
                "page": fc.get("page"),
            }
        )
    return rows


def extract_one(
    llm_client: LLMClient, gcs_client, bucket: str, doc: dict, purpose_prefix: str = "extract"
) -> dict:
    """doc: {doc_id, processor_id, doc_type, gcs_path}."""
    doc_type = doc["doc_type"]
    schema = SCHEMA_BY_DOC_TYPE[doc_type]
    prompt = PROMPT_BY_DOC_TYPE[doc_type]
    mime_type = MIME_TYPE_BY_DOC_TYPE[doc_type]
    purpose = f"{purpose_prefix}:{doc_type}"

    data = gcs.download_bytes(gcs_client, bucket, doc["gcs_path"])

    last_error: Exception | None = None
    for attempt in range(2):  # one retry on schema-validation failure only
        try:
            facts = llm_client.extract(data, mime_type, prompt, schema, purpose=purpose)
            return {
                "doc_id": doc["doc_id"],
                "processor_id": doc["processor_id"],
                "doc_type": doc_type,
                "status": "ok",
                "facts": facts,
                "error": None,
            }
        except ValidationError as exc:
            last_error = exc
            logger.warning(
                "extraction schema validation failed for %s (attempt %d): %s",
                doc["doc_id"],
                attempt + 1,
                exc,
            )
        except Exception as exc:  # noqa: BLE001 — any other failure also ends this document
            last_error = exc
            logger.warning("extraction failed for %s: %s", doc["doc_id"], exc)
            break

    return {
        "doc_id": doc["doc_id"],
        "processor_id": doc["processor_id"],
        "doc_type": doc_type,
        "status": "failed",
        "facts": None,
        "error": str(last_error),
    }


def extract_all(
    llm_client: LLMClient,
    gcs_client,
    bucket: str,
    docs: list[dict],
    purpose_prefix: str = "extract",
) -> list[dict]:
    results = []
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = {
            executor.submit(extract_one, llm_client, gcs_client, bucket, doc, purpose_prefix): doc
            for doc in docs
        }
        for future in as_completed(futures):
            results.append(future.result())
    return results
