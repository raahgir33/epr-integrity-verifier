"""Metrics vs ground truth. Currently just extraction field accuracy — T6's
gate. T14 adds the rest of docs/DATA_SPEC.md §7's metrics (detection
precision/recall, tonnage error, agent contribution, etc.) on top of this,
not as a replacement for it.
"""

import math

# Every field except free-text ones (item_description, address, names,
# categories, remarks) — the "key numeric and ID fields" the T6 gate is
# measured against (docs/BUILD_PLAN.md T6).
KEY_FIELDS_BY_DOC_TYPE: dict[str, set[str]] = {
    "cto": {"consent_no", "capacity_t_per_year", "valid_from", "valid_to"},
    "epr_registration": {"registration_no", "capacity_t_per_year"},
    "inbound_invoice": {
        "invoice_no",
        "date",
        "supplier_gstin",
        "buyer_gstin",
        "hsn",
        "quantity_t",
        "rate",
        "value",
    },
    "eway_bill": {
        "ewb_no",
        "generated_at",
        "valid_until",
        "from_gstin",
        "to_gstin",
        "from_pin",
        "to_pin",
        "distance_km",
        "vehicle_no",
        "hsn",
        "quantity_t",
        "value",
        "invoice_no",
    },
    "weighbridge_slip": {
        "ticket_no",
        "vehicle_no",
        "gross_kg",
        "tare_kg",
        "net_kg",
        "in_time",
        "out_time",
    },
    "outbound_invoice": {"invoice_no", "date", "hsn", "quantity_t"},
    "electricity_bill": {"billing_month", "units_consumed_kwh", "connected_load_kw"},
}


def extraction_field_accuracy(extracted_rows: list[dict], ground_truth_docs: list[dict]) -> dict:
    """extracted_rows: extracted_facts-shaped dicts (doc_id, field_name,
    printed_value, ...). ground_truth_docs: ground_truth.json's "documents"
    list (doc_id, doc_type, fields: {name: {printed, canonical}}).

    Returns {doc_type: {correct, total, accuracy}, ..., "overall": {...}}.
    Pure function — no I/O — so it's unit-testable without BigQuery.
    """
    gt_by_doc = {d["doc_id"]: d for d in ground_truth_docs}
    rows_by_doc: dict[str, list[dict]] = {}
    for row in extracted_rows:
        rows_by_doc.setdefault(row["doc_id"], []).append(row)

    per_type: dict[str, dict[str, int]] = {}
    for doc_id, rows in rows_by_doc.items():
        gt_doc = gt_by_doc.get(doc_id)
        if gt_doc is None:
            continue
        doc_type = gt_doc["doc_type"]
        key_fields = KEY_FIELDS_BY_DOC_TYPE.get(doc_type, set())
        gt_fields = gt_doc["fields"]
        extracted_by_field = {r["field_name"]: r["printed_value"] for r in rows}

        stats = per_type.setdefault(doc_type, {"correct": 0, "total": 0})
        for field_name in key_fields:
            if field_name not in gt_fields:
                continue
            gt_value = gt_fields[field_name]["printed"]
            extracted_value = extracted_by_field.get(field_name)
            stats["total"] += 1
            if extracted_value is not None and extracted_value.strip() == gt_value.strip():
                stats["correct"] += 1

    report: dict[str, dict] = {}
    overall_correct = 0
    overall_total = 0
    for doc_type, stats in per_type.items():
        accuracy = stats["correct"] / stats["total"] if stats["total"] else None
        report[doc_type] = {
            "correct": stats["correct"],
            "total": stats["total"],
            "accuracy": accuracy,
        }
        overall_correct += stats["correct"]
        overall_total += stats["total"]

    report["overall"] = {
        "correct": overall_correct,
        "total": overall_total,
        "accuracy": overall_correct / overall_total if overall_total else None,
    }
    return report


def extraction_field_mismatches(
    extracted_rows: list[dict], ground_truth_docs: list[dict]
) -> list[dict]:
    """Same inputs/matching rules as extraction_field_accuracy, but returns
    the actual mismatched (doc_id, field_name) pairs instead of just
    counts — one dict per mismatch: {doc_id, processor_id, doc_type,
    field_name, extracted_value, truth_value}. extracted_value is None
    when the field is a key field but Gemini's output didn't include it
    at all (as opposed to a wrong value). Pure function — no I/O."""
    gt_by_doc = {d["doc_id"]: d for d in ground_truth_docs}
    rows_by_doc: dict[str, list[dict]] = {}
    for row in extracted_rows:
        rows_by_doc.setdefault(row["doc_id"], []).append(row)

    mismatches: list[dict] = []
    for doc_id, rows in rows_by_doc.items():
        gt_doc = gt_by_doc.get(doc_id)
        if gt_doc is None:
            continue
        doc_type = gt_doc["doc_type"]
        key_fields = KEY_FIELDS_BY_DOC_TYPE.get(doc_type, set())
        gt_fields = gt_doc["fields"]
        extracted_by_field = {r["field_name"]: r["printed_value"] for r in rows}

        for field_name in key_fields:
            if field_name not in gt_fields:
                continue
            gt_value = gt_fields[field_name]["printed"]
            extracted_value = extracted_by_field.get(field_name)
            if extracted_value is not None and extracted_value.strip() == gt_value.strip():
                continue
            mismatches.append(
                {
                    "doc_id": doc_id,
                    "processor_id": gt_doc.get("processor_id"),
                    "doc_type": doc_type,
                    "field_name": field_name,
                    "extracted_value": extracted_value,
                    "truth_value": gt_value,
                }
            )
    return mismatches


def format_accuracy_pct(correct: int, total: int) -> str:
    """2-decimal-place percentage, truncated (never rounded) so a
    not-quite-perfect ratio can never print as "100.00%" — e.g. 5521/5523
    (99.9638...%) must read "99.96%", not round up at either the 1- or
    2-decimal boundary. Exact equality is the only path to "100.00%"."""
    if total == 0:
        return "n/a"
    if correct == total:
        return "100.00%"
    pct = correct / total * 100
    truncated = math.floor(pct * 100) / 100
    return f"{truncated:.2f}%"
