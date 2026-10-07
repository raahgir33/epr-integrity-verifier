"""The 5 Critic tools (docs/ARCHITECTURE.md §4): run_check,
get_document_facts, get_shipments, get_site_assessment, read_document.

build_tools(processor_context) closes over this processor's already-fetched
data so only read_document does any I/O per call (document bytes can't be
preloaded into context — there are too many, and most are never read).
processor_context is a plain dict assembled by the caller (never by
anything in app/ reading ground_truth.json directly — see
docs/PROGRESS.md's T10 leak-guard note); this module has no opinion on
where it came from.

Every tool returns (summary, attachment) — attachment is (bytes, mime_type)
for read_document, None for every other tool (app/llm.py's run_tool_loop
contract). Summaries are capped at ~2 KB (ARCHITECTURE.md §4) — short
enough to keep the tool loop's growing conversation cheap, never a whole
table.
"""

import json
from collections.abc import Callable

from app.store import gcs

_SUMMARY_CAP_BYTES = 2048


def _cap(value) -> str:
    text = json.dumps(value, default=str)
    if len(text.encode("utf-8")) <= _SUMMARY_CAP_BYTES:
        return text
    return text[:_SUMMARY_CAP_BYTES] + "...(truncated)"


def _parse_gcs_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError(f"not a gs:// URI: {uri!r}")
    bucket, _, blob_path = uri.removeprefix("gs://").partition("/")
    return bucket, blob_path


def build_tools(processor_context: dict, gcs_client=None) -> list[Callable]:
    """processor_context: {"check_results": [...], "shipments": [...],
    "site_assessment": dict | None, "documents": [{"doc_id", "doc_type",
    "lang", "gcs_path", "fields": {field_name: printed_value}}]}. Every
    field here must be document-observable — never a ground-truth-only
    label (is_f8, verified, issue_types, true_*, risk_band, placement
    notes). gcs_client is only needed for read_document; omit for tests
    that never call it.
    """
    check_results_by_id = {c["check_id"]: c for c in processor_context.get("check_results", [])}
    shipments_by_id = {s["shipment_id"]: s for s in processor_context.get("shipments", [])}
    documents_by_id = {d["doc_id"]: d for d in processor_context.get("documents", [])}
    site_assessment = processor_context.get("site_assessment")

    def run_check(check_id: str):
        """Returns this processor's already-computed result for one
        deterministic check (e.g. "C1", "C4") — status, measured value,
        threshold, and explanation. Checks are precomputed once per
        pipeline run, not re-executed on demand."""
        result = check_results_by_id.get(check_id)
        if result is None:
            return _cap({"error": f"no check result for {check_id}"}), None
        return _cap(result), None

    def get_shipments(shipment_ids: list[str]):
        """Returns match status, quantities, dates and transport details
        for the given shipment IDs. Unknown IDs are silently omitted."""
        found = [shipments_by_id[sid] for sid in shipment_ids if sid in shipments_by_id]
        return _cap(found), None

    def get_document_facts(doc_id: str):
        """Returns one document's type, language and printed field values
        by its document ID."""
        doc = documents_by_id.get(doc_id)
        if doc is None:
            return _cap({"error": f"no document {doc_id}"}), None
        return (
            _cap(
                {
                    "doc_id": doc_id,
                    "doc_type": doc.get("doc_type"),
                    "lang": doc.get("lang"),
                    "fields": doc.get("fields"),
                }
            ),
            None,
        )

    def get_site_assessment():
        """Returns this processor's site plausibility result (building
        footprint, status, explanation), if one has been computed."""
        if site_assessment is None:
            return _cap({"error": "no site assessment available for this processor"}), None
        return _cap(site_assessment), None

    def read_document(doc_id: str):
        """Fetches one document's raw file (PDF or image) by its document
        ID so you can read it directly, for example to check wording a
        summary wouldn't capture."""
        doc = documents_by_id.get(doc_id)
        if doc is None or not doc.get("gcs_path"):
            return _cap({"error": f"no document {doc_id}"}), None
        bucket, blob_path = _parse_gcs_uri(doc["gcs_path"])
        data = gcs.download_bytes(gcs_client, bucket, blob_path)
        mime_type = doc.get("mime_type") or (
            "image/png" if doc.get("doc_type") == "weighbridge_slip" else "application/pdf"
        )
        return _cap({"doc_id": doc_id, "note": "document attached"}), (data, mime_type)

    return [run_check, get_shipments, get_document_facts, get_site_assessment, read_document]
