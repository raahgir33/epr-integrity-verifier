"""Joins invoice, e-way bill and weighbridge records into shipments;
outputs and energy into their own tables. Two modes:

- truth: reshapes the generator's own ground_truth.json shipments/outputs/
  energy_monthly directly — already matched at generation time, so no
  matching algorithm runs, and T8/T10 can be built before T6 finishes.
- extracted: joins real extracted_facts rows using docs/DATA_SPEC.md §4's
  matching rules (invoice<->e-way by invoice number + supplier GSTIN;
  e-way<->weighbridge by vehicle number and time window, earliest wins),
  via units.py to parse the printed values.
"""

import datetime

from app.ingest import units

TRUTH = "truth"
EXTRACTED = "extracted"

# Infix that marks a T13 demo-extra document (e.g.
# "PWP-03-DEMO-INBOUND_INVOICE-001") apart from a dossier document
# ("PWP-03-INBOUND_INVOICE-003"). Also the key app/admin/reset_demo.py
# uses to find the shipments a demo run created.
_DEMO_DOC_MARKER = "-DEMO-"


def _safe_number(printed: str | None) -> float | None:
    if printed is None:
        return None
    try:
        return units.parse_indian_number(printed)
    except ValueError:
        return None


def _safe_datetime(printed: str | None) -> datetime.datetime | None:
    if printed is None:
        return None
    try:
        return units.parse_datetime_ist(printed)
    except ValueError:
        return None


def _to_utc_iso(dt: datetime.datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(datetime.UTC).isoformat()


# ---------- truth mode: direct reshape, no matching needed ----------


def shipments_from_truth(
    seed: int, processor_id: str, truth_shipments: list[dict], documents: list[dict]
) -> list[dict]:
    """documents: ground_truth.json's top-level "documents" list (any
    processor's — doc_ids are globally unique), used only to look up the
    document-content fields (invoice_no, supplier_gstin, weighbridge ticket
    number, e-way/weighbridge timestamps) that the generator's shipment
    dicts don't carry directly.

    These lookups read each field's "printed" value and parse it through
    the same units.py functions extracted mode uses — not "canonical",
    which carries sub-minute precision (seconds, microseconds) that never
    appears on the printed document and that a real extraction could never
    recover. Using canonical here would make this shipment's timing fields
    permanently disagree with match_shipments_from_extracted's, even for a
    perfect extraction — see the T7 F4 decision in docs/PROGRESS.md for the
    same principle applied to a different field.
    """
    docs_by_id = {d["doc_id"]: d for d in documents}

    def _printed(doc_id: str | None, field: str) -> str | None:
        if doc_id is None:
            return None
        return docs_by_id.get(doc_id, {}).get("fields", {}).get(field, {}).get("printed")

    rows = []
    for s in truth_shipments:
        invoice_doc_id = s.get("invoice_doc_id")
        eway_doc_id = s.get("eway_doc_id")
        weighbridge_doc_id = s.get("weighbridge_doc_id")
        rows.append(
            {
                "seed": seed,
                "facts_source": TRUTH,
                "shipment_id": s["shipment_id"],
                "processor_id": processor_id,
                "month": s.get("month"),
                "invoice_doc_id": invoice_doc_id,
                "eway_doc_id": eway_doc_id,
                "weighbridge_doc_id": weighbridge_doc_id,
                "invoice_qty_t": s.get("invoice_qty_t"),
                "weighbridge_net_t": s.get("weighbridge_net_t"),
                "match_status": s.get("match_status"),
                "ewb_no": s.get("ewb_no"),
                "vehicle_no": s.get("vehicle_no"),
                "distance_km": s.get("distance_km"),
                "eway_generated_at": _to_utc_iso(
                    _safe_datetime(_printed(eway_doc_id, "generated_at"))
                ),
                "eway_valid_until": _to_utc_iso(
                    _safe_datetime(_printed(eway_doc_id, "valid_until"))
                ),
                "weighbridge_in_time": _to_utc_iso(
                    _safe_datetime(_printed(weighbridge_doc_id, "in_time"))
                ),
                "invoice_no": _printed(invoice_doc_id, "invoice_no"),
                "supplier_gstin": _printed(invoice_doc_id, "supplier_gstin"),
                "weighbridge_ticket_no": _printed(weighbridge_doc_id, "ticket_no"),
            }
        )
    return rows


def outputs_from_truth(seed: int, processor_id: str, truth_outputs: list[dict]) -> list[dict]:
    return [
        {
            "seed": seed,
            "facts_source": TRUTH,
            "doc_id": o["doc_id"],
            "processor_id": processor_id,
            "month": o["month"],
            "quantity_t": o["quantity_t"],
        }
        for o in truth_outputs
    ]


def energy_from_truth(seed: int, processor_id: str, truth_energy: list[dict]) -> list[dict]:
    return [
        {
            "seed": seed,
            "facts_source": TRUTH,
            "doc_id": e["doc_id"],
            "processor_id": processor_id,
            "month": e["month"],
            "kwh": e["kwh"],
        }
        for e in truth_energy
    ]


# ---------- extracted mode: real matching, docs/DATA_SPEC.md §4 ----------


def facts_by_doc_id(extracted_rows: list[dict]) -> dict[str, dict[str, str]]:
    """extracted_facts-shaped rows -> {doc_id: {field_name: printed_value}}."""
    result: dict[str, dict[str, str]] = {}
    for row in extracted_rows:
        result.setdefault(row["doc_id"], {})[row["field_name"]] = row["printed_value"]
    return result


def match_shipments_from_extracted(
    seed: int,
    processor_id: str,
    documents: list[dict],
    facts: dict[str, dict[str, str]],
) -> list[dict]:
    """documents: this processor's {doc_id, doc_type} records.
    facts: doc_id -> {field_name: printed_value}, from facts_by_doc_id.
    """
    # Sorted by doc_id, and demo-extra invoices held back into their own
    # numbering below. Both matter because the shipment_id is positional
    # (`enumerate(invoices)`), while `documents` arrives straight off a
    # BigQuery SELECT with no ORDER BY — so row order, and therefore every
    # shipment_id, was whatever that query happened to return. Confirmed
    # live (2026-10-15): a run on PWP-03 renumbered its shipments against
    # the pre-demo snapshot with no demo documents involved at all
    # (SHP-001 moved from INBOUND_INVOICE-003 to -009, SHP-008 the other
    # way), which silently repoints the restored snapshot's agent findings
    # at different physical shipments.
    #
    # doc_id order is the canonical numbering, not an arbitrary choice:
    # every shipment_id currently stored satisfies SHP-{i} <->
    # INBOUND_INVOICE-{3i}, verified against PWP-01/02/03/05/08's own
    # stored findings and trails, so sorting here reproduces the IDs
    # already in BigQuery rather than renaming them.
    invoices = sorted(
        (d for d in documents if d["doc_type"] == "inbound_invoice"), key=lambda d: d["doc_id"]
    )
    eway_bills = sorted(
        (d for d in documents if d["doc_type"] == "eway_bill"), key=lambda d: d["doc_id"]
    )
    weighbridge_slips = sorted(
        (d for d in documents if d["doc_type"] == "weighbridge_slip"), key=lambda d: d["doc_id"]
    )

    # Rule 1: invoice <-> e-way bill, by invoice number + supplier GSTIN.
    eway_by_key: dict[tuple[str | None, str | None], list[dict]] = {}
    for e in eway_bills:
        f = facts.get(e["doc_id"], {})
        key = (f.get("invoice_no"), f.get("from_gstin"))
        eway_by_key.setdefault(key, []).append(e)

    used_weighbridge_doc_ids: set[str] = set()
    shipments = []

    # T13's demo-extra invoices get their own numbering, so adding one
    # never shifts an existing -EXT-SHP- id. Without this, the demo
    # invoice sorts ahead of every real one ("-DEMO-" < "-INBOUND_") and
    # takes SHP-001, pushing the whole dossier down by one — and the
    # pre-demo snapshot's restored findings cite those ids. The id this
    # produces is the one the generator's own manifest already declares
    # for the shipment ("PWP-03-DEMO-SHP-001"), so the two now agree.
    # Plain invoices are numbered and matched first, leaving their
    # weighbridge-slip claims (used_weighbridge_doc_ids) in exactly the
    # order they had before demo documents existed.
    plain_invoices = [d for d in invoices if _DEMO_DOC_MARKER not in d["doc_id"]]
    demo_invoices = [d for d in invoices if _DEMO_DOC_MARKER in d["doc_id"]]
    numbered = [
        (f"{processor_id}-EXT-SHP-{i:03d}", inv) for i, inv in enumerate(plain_invoices, start=1)
    ]
    numbered += [
        (f"{processor_id}-DEMO-SHP-{i:03d}", inv) for i, inv in enumerate(demo_invoices, start=1)
    ]

    for shipment_id, inv in numbered:
        inv_facts = facts.get(inv["doc_id"], {})
        key = (inv_facts.get("invoice_no"), inv_facts.get("supplier_gstin"))
        candidates = eway_by_key.get(key, [])
        eway_doc = candidates[0] if candidates else None
        eway_facts = facts.get(eway_doc["doc_id"], {}) if eway_doc else {}

        # Rule 2: e-way bill <-> weighbridge slip, by vehicle number and
        # time window (in-time after generation, before valid-until + 3
        # days); earliest such slip wins.
        weighbridge_doc = None
        generated_at = None
        valid_until = None
        if eway_doc:
            vehicle_no = eway_facts.get("vehicle_no")
            generated_at = _safe_datetime(eway_facts.get("generated_at"))
            valid_until = _safe_datetime(eway_facts.get("valid_until"))
            if vehicle_no and generated_at and valid_until:
                deadline = valid_until + datetime.timedelta(days=3)
                matches = []
                for w in weighbridge_slips:
                    if w["doc_id"] in used_weighbridge_doc_ids:
                        continue
                    w_facts = facts.get(w["doc_id"], {})
                    if w_facts.get("vehicle_no") != vehicle_no:
                        continue
                    in_time = _safe_datetime(w_facts.get("in_time"))
                    if in_time and generated_at < in_time < deadline:
                        matches.append((in_time, w))
                if matches:
                    matches.sort(key=lambda m: m[0])
                    weighbridge_doc = matches[0][1]
                    used_weighbridge_doc_ids.add(weighbridge_doc["doc_id"])

        weighbridge_net_t = None
        weighbridge_ticket_no = None
        weighbridge_in_time = None
        if weighbridge_doc:
            w_facts = facts.get(weighbridge_doc["doc_id"], {})
            net_kg = _safe_number(w_facts.get("net_kg"))
            weighbridge_net_t = units.kg_to_t(net_kg) if net_kg is not None else None
            weighbridge_ticket_no = w_facts.get("ticket_no")
            weighbridge_in_time = _safe_datetime(w_facts.get("in_time"))

        month = None
        invoice_date = inv_facts.get("date")
        if invoice_date:
            try:
                month = units.parse_date_ddmmyyyy(invoice_date).strftime("%Y-%m")
            except ValueError:
                month = None

        shipments.append(
            {
                "seed": seed,
                "facts_source": EXTRACTED,
                "shipment_id": shipment_id,
                "processor_id": processor_id,
                "month": month,
                "invoice_doc_id": inv["doc_id"],
                "eway_doc_id": eway_doc["doc_id"] if eway_doc else None,
                "weighbridge_doc_id": weighbridge_doc["doc_id"] if weighbridge_doc else None,
                "invoice_qty_t": _safe_number(inv_facts.get("quantity_t")),
                "weighbridge_net_t": weighbridge_net_t,
                "match_status": "matched" if weighbridge_doc else "unmatched",
                "ewb_no": eway_facts.get("ewb_no") if eway_doc else None,
                "vehicle_no": eway_facts.get("vehicle_no") if eway_doc else None,
                "distance_km": _safe_number(eway_facts.get("distance_km")) if eway_doc else None,
                "eway_generated_at": _to_utc_iso(generated_at),
                "eway_valid_until": _to_utc_iso(valid_until),
                "weighbridge_in_time": _to_utc_iso(weighbridge_in_time),
                "invoice_no": inv_facts.get("invoice_no"),
                "supplier_gstin": inv_facts.get("supplier_gstin"),
                "weighbridge_ticket_no": weighbridge_ticket_no,
            }
        )

    return shipments


def outputs_from_extracted(
    seed: int, processor_id: str, documents: list[dict], facts: dict[str, dict[str, str]]
) -> list[dict]:
    """One row per outbound_invoice document — no matching needed."""
    rows = []
    for d in documents:
        if d["doc_type"] != "outbound_invoice":
            continue
        f = facts.get(d["doc_id"], {})
        month = None
        if f.get("date"):
            try:
                month = units.parse_date_ddmmyyyy(f["date"]).strftime("%Y-%m")
            except ValueError:
                month = None
        rows.append(
            {
                "seed": seed,
                "facts_source": EXTRACTED,
                "doc_id": d["doc_id"],
                "processor_id": processor_id,
                "month": month,
                "quantity_t": _safe_number(f.get("quantity_t")),
            }
        )
    return rows


def energy_from_extracted(
    seed: int, processor_id: str, documents: list[dict], facts: dict[str, dict[str, str]]
) -> list[dict]:
    """One row per electricity_bill document — billing_month is already
    printed as "YYYY-MM", no parsing needed."""
    rows = []
    for d in documents:
        if d["doc_type"] != "electricity_bill":
            continue
        f = facts.get(d["doc_id"], {})
        rows.append(
            {
                "seed": seed,
                "facts_source": EXTRACTED,
                "doc_id": d["doc_id"],
                "processor_id": processor_id,
                "month": f.get("billing_month"),
                "kwh": _safe_number(f.get("units_consumed_kwh")),
            }
        )
    return rows
