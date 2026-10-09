"""Builds one extra, realistic, fully-matched shipment per demo processor
for T13's live event path — content that exists nowhere in the committed
seed-42 dossier and is deliberately never added to ground_truth.json, so
it can never leak into extraction accuracy / detection eval metrics
(both are keyed by doc_id against ground_truth.json's own document list,
and silently skip an unknown doc_id — app/eval/evaluate.py).

Design, decided with the developer (docs/PROGRESS.md, T13 plan):
- Reuses shipments.py's own field-construction helpers (pc, fmt_date,
  fmt_datetime, format_indian_number, haversine_km, month_bounds,
  _VEHICLE_CLASSES, _HSN_WASTE, _NORMAL_DESCRIPTIONS_EN) — same formulas,
  same realism, as any ordinary shipment in the main dataset. Never calls
  build_dossier()/build_processors()/build_suppliers() or touches the
  seeded rng stream those use — this module reads already-committed
  processors.json/suppliers.json/ground_truth.json and derives everything
  it needs (same-state supplier pool, "next in series" invoice_no/ewb_no/
  ticket_no) from that committed data directly, so it can never disturb
  or depend on the main generator's own rng sequencing.
- The new shipment's month is always the dataset's own as_of_month (the
  financial year's last month, FY_MONTHS[-1], "2026-03") — not a new
  fiscal year — so it folds directly into the SAME FY-to-date figures
  already shown on the live dashboard (certified_t_fy_to_date's FY
  window is strict: a literal next-calendar-month value would start a
  new, disconnected FY and never sum with the existing headline numbers;
  see the T13 plan's decision).
- Dated in the 26th-28th of that month specifically, so it's always
  after every regular shipment's own day draw (1-25) without needing to
  inspect any sibling shipment's actual date.
- invoice_no/ewb_no/ticket_no are each the next value in that supplier's/
  the dataset's/that processor's own real series — never invented,
  never colliding with a real document's identifiers.
"""

import datetime
import random

from app.checks import params
from scripts.dossier_gen.shipments import (
    _HSN_WASTE,
    _NORMAL_DESCRIPTIONS_EN,
    _VEHICLE_CLASSES,
    fmt_date,
    fmt_datetime,
    format_indian_number,
    haversine_km,
    month_bounds,
    pc,
)

_MIN_SUPPLIER_DISTANCE_KM = 25.0
_DEMO_DAY_CHOICES = (26, 27, 28)


def same_state_suppliers_with_history(
    processor: dict, suppliers: list[dict], ground_truth_docs: list[dict]
) -> list[dict]:
    """Same-state (by GSTIN state-code prefix — processors.json/
    suppliers.json don't expose the generator-internal `state` field, but
    gstin[:2] already encodes it), >= _MIN_SUPPLIER_DISTANCE_KM from this
    processor's site (same reasoning as shipments.py's own supplier
    filter — a too-close supplier risks a sub-minute true transit time
    that printed-minute rounding could swing past MAX_AVG_SPEED_KMPH),
    and restricted to suppliers with at least one real invoice already in
    ground_truth_docs (so this module can always derive a real "next
    invoice_no in series" for whichever supplier is picked)."""
    invoiced_gstins = {
        d["fields"]["supplier_gstin"]["canonical"]
        for d in ground_truth_docs
        if d["doc_type"] == "inbound_invoice"
    }
    return [
        s
        for s in suppliers
        if s["gstin"][:2] == processor["gstin"][:2]
        and s["gstin"] in invoiced_gstins
        and haversine_km(s["lat"], s["lon"], processor["lat"], processor["lon"])
        >= _MIN_SUPPLIER_DISTANCE_KM
    ]


def next_invoice_no(supplier: dict, ground_truth_docs: list[dict]) -> str:
    """This supplier's existing invoice_no series (shipments.py's
    assign_cross_processor_identifiers: f"{prefix}/25-26/{seq:04d}",
    monotonic per supplier across every processor) plus one — derived by
    counting, not by re-running that cross-processor pass."""
    existing = [
        d["fields"]["invoice_no"]["canonical"]
        for d in ground_truth_docs
        if d["doc_type"] == "inbound_invoice"
        and d["fields"]["supplier_gstin"]["canonical"] == supplier["gstin"]
    ]
    if not existing:
        raise ValueError(
            f"supplier {supplier['gstin']} has no existing invoice to derive a prefix from"
        )
    prefix = existing[0].split("/")[0]
    return f"{prefix}/25-26/{len(existing) + 1:04d}"


def next_ewb_no(ground_truth_docs: list[dict], rng: random.Random) -> str:
    """One shared global series (shipments.py: a single counter, not per-
    supplier/processor) — the real algorithm's own increment band
    (100-5000) reused here, applied to the dataset's current maximum
    rather than replaying the real algorithm's own running total."""
    existing_max = max(
        int(d["fields"]["ewb_no"]["canonical"])
        for d in ground_truth_docs
        if d["doc_type"] == "eway_bill"
    )
    return str(existing_max + rng.randint(100, 5000))


def processor_pin_code(processor_id: str, ground_truth_docs: list[dict]) -> str:
    """processors.json doesn't expose pin_code (generator-internal,
    manifests.py's processors_to_json omits it) — recovered from any of
    this processor's own existing e-way bills' to_pin field instead,
    which is constant per processor across every shipment."""
    existing = [
        d["fields"]["to_pin"]["canonical"]
        for d in ground_truth_docs
        if d["doc_type"] == "eway_bill" and d["processor_id"] == processor_id
    ]
    if not existing:
        raise ValueError(f"{processor_id} has no existing e-way bill to derive a PIN code from")
    return existing[0]


def next_ticket_no(processor_id: str, ground_truth_docs: list[dict]) -> str:
    """One physical weighbridge per site (shipments.py) — weighbridge_code
    recovered from any of this processor's own existing tickets (format
    "{weighbridge_code}-{seq:05d}"), never guessed."""
    existing = [
        d["fields"]["ticket_no"]["canonical"]
        for d in ground_truth_docs
        if d["doc_type"] == "weighbridge_slip" and d["processor_id"] == processor_id
    ]
    if not existing:
        raise ValueError(f"{processor_id} has no existing weighbridge ticket to derive a code from")
    weighbridge_code = existing[0].rsplit("-", 1)[0]
    return f"{weighbridge_code}-{len(existing) + 1:05d}"


def build_demo_extra_shipment(
    processor: dict,
    supplier: dict,
    rng: random.Random,
    month: str,
    invoice_no: str,
    ewb_no: str,
    ticket_no: str,
    to_pin: str,
    remark_hi: str | None = None,
) -> tuple[list[dict], dict]:
    """Builds one realistic, fully-matched shipment (invoice + e-way bill
    + weighbridge slip documents, plus a shipment record) — same field
    formulas as an ordinary shipment in shipments.py's build_dossier, just
    for exactly one shipment outside the normal per-processor build.
    remark_hi, when given, becomes the weighbridge slip's handwritten
    remark (rendered as a Pillow overlay at render time, same mechanism
    as the real F9/H5 — not drawn here); every other printed field,
    including net weight, is unaffected by it, matching F9/H5's own
    design (DATA_SPEC.md §5).

    processor/supplier are plain dicts from processors.json/
    suppliers.json (gstin, address/pin_code/lat/lon as applicable).
    Returns (documents, shipment) — documents each shaped
    {doc_id, doc_type, processor_id, lang, fields}, doc_id always
    "{processor_id}-DEMO-{DOC_TYPE}-001" (never collides with a real
    doc_id, which is never "-DEMO-"-infixed)."""
    pid = processor["processor_id"]
    start, _end = month_bounds(month)
    day = rng.choice(_DEMO_DAY_CHOICES)
    invoice_date = start + datetime.timedelta(days=day - 1)
    # The real F9 instance (PWP-02) keeps every typed template field in
    # English — lang="en" throughout — with only the weighbridge remark
    # itself carrying Hindi text (handled by the Kalam overlay
    # independent of the template's own lang); confirmed against
    # ground_truth.json rather than assumed. remark_hi never changes the
    # surrounding documents' language.
    lang = "en"
    desc = _NORMAL_DESCRIPTIONS_EN[0]

    vehicle_class = "heavy_multiaxle" if rng.random() < 0.3 else "light_2axle"
    net_t_range = _VEHICLE_CLASSES[vehicle_class]["net_t"]
    qty_t = round(rng.uniform(*net_t_range), 2)
    # ASSUMPTION, same band as shipments.py's own (unsourced scrap pricing).
    rate = round(rng.uniform(8, 18), 2)
    value = round(qty_t * 1000 * rate, 2)

    def doc_id(doc_type: str) -> str:
        return f"{pid}-DEMO-{doc_type.upper()}-001"

    invoice_doc = {
        "doc_id": doc_id("inbound_invoice"),
        "doc_type": "inbound_invoice",
        "processor_id": pid,
        "lang": lang,
        "fields": {
            "invoice_no": pc(invoice_no, invoice_no),
            "date": pc(fmt_date(invoice_date), invoice_date.isoformat()),
            "supplier_gstin": pc(supplier["gstin"], supplier["gstin"]),
            "buyer_gstin": pc(processor["gstin"], processor["gstin"]),
            "item_description": pc(desc, desc),
            "hsn": pc(_HSN_WASTE, _HSN_WASTE),
            "quantity_t": pc(format_indian_number(qty_t), qty_t),
            "rate": pc(format_indian_number(rate), rate),
            "value": pc(format_indian_number(value), value),
        },
    }

    raw_km = haversine_km(supplier["lat"], supplier["lon"], processor["lat"], processor["lon"])
    distance_km = round(raw_km * params.ROAD_FACTOR * rng.uniform(0.95, 1.1), 1)
    avg_speed = rng.uniform(30, 48)
    transit_hours = distance_km / avg_speed
    generated_at = datetime.datetime.combine(
        invoice_date, datetime.time(rng.randint(8, 11), rng.randint(0, 59))
    )
    weighbridge_in = generated_at + datetime.timedelta(hours=transit_hours)
    ewb_valid_days = -(-int(distance_km) // 200)
    valid_until = datetime.datetime.combine(
        generated_at.date() + datetime.timedelta(days=ewb_valid_days), datetime.time(23, 59, 59)
    )
    state_abbr = rng.choice(["MH", "GJ", "TN", "TG", "MP", "HR", "RJ"])
    vehicle_no = f"{state_abbr}{rng.randint(10, 59):02d}AB{rng.randint(1000, 9999)}"

    eway_doc = {
        "doc_id": doc_id("eway_bill"),
        "doc_type": "eway_bill",
        "processor_id": pid,
        "lang": lang,
        "fields": {
            "ewb_no": pc(ewb_no, ewb_no),
            "generated_at": pc(fmt_datetime(generated_at), generated_at.isoformat()),
            "valid_until": pc(fmt_datetime(valid_until), valid_until.isoformat()),
            "from_gstin": pc(supplier["gstin"], supplier["gstin"]),
            "to_gstin": pc(processor["gstin"], processor["gstin"]),
            "from_pin": pc(supplier["pin_code"], supplier["pin_code"]),
            "to_pin": pc(to_pin, to_pin),
            "distance_km": pc(f"{distance_km:.1f}", distance_km),
            "vehicle_no": pc(vehicle_no, vehicle_no),
            "hsn": pc(_HSN_WASTE, _HSN_WASTE),
            "quantity_t": pc(format_indian_number(qty_t), qty_t),
            "value": pc(format_indian_number(value), value),
            "invoice_no": pc(invoice_no, invoice_no),
        },
    }

    net_t = round(qty_t * rng.uniform(0.988, 1.012), 2)
    tare_kg = round(rng.uniform(*_VEHICLE_CLASSES[vehicle_class]["tare_kg"]), 0)
    net_kg = net_t * 1000
    gross_kg = net_kg + tare_kg
    out_time = weighbridge_in + datetime.timedelta(minutes=rng.randint(15, 45))
    remark_text = remark_hi or ""

    weighbridge_doc = {
        "doc_id": doc_id("weighbridge_slip"),
        "doc_type": "weighbridge_slip",
        "processor_id": pid,
        "lang": lang,
        "fields": {
            "ticket_no": pc(ticket_no, ticket_no),
            "vehicle_no": pc(vehicle_no, vehicle_no),
            "gross_kg": pc(format_indian_number(gross_kg, 0), gross_kg),
            "tare_kg": pc(format_indian_number(tare_kg, 0), tare_kg),
            "net_kg": pc(format_indian_number(net_kg, 0), net_kg),
            "in_time": pc(fmt_datetime(weighbridge_in), weighbridge_in.isoformat()),
            "out_time": pc(fmt_datetime(out_time), out_time.isoformat()),
            "remarks": pc(remark_text, remark_text),
        },
    }

    shipment = {
        "shipment_id": f"{pid}-DEMO-SHP-001",
        "month": month,
        "invoice_doc_id": invoice_doc["doc_id"],
        "eway_doc_id": eway_doc["doc_id"],
        "weighbridge_doc_id": weighbridge_doc["doc_id"],
        "invoice_qty_t": qty_t,
        "weighbridge_net_t": net_t,
        "match_status": "matched",
        "ewb_no": ewb_no,
        "vehicle_no": vehicle_no,
        "distance_km": distance_km,
        "verified": True,
    }

    return [invoice_doc, eway_doc, weighbridge_doc], shipment


def plan_demo_extra_shipment(
    processor: dict,
    suppliers: list[dict],
    ground_truth_docs: list[dict],
    rng: random.Random,
    as_of_month: str,
    remark_hi: str | None = None,
) -> tuple[list[dict], dict]:
    """Picks a supplier and derives invoice_no/ewb_no/ticket_no from the
    committed dataset, then calls build_demo_extra_shipment. Raises
    ValueError (loudly, not a silent fallback) if this processor has no
    eligible same-state supplier with invoice history — the caller should
    treat that as a configuration problem to fix, not paper over."""
    candidates = same_state_suppliers_with_history(processor, suppliers, ground_truth_docs)
    if not candidates:
        raise ValueError(f"no eligible demo-extra supplier for {processor['processor_id']}")
    supplier = rng.choice(candidates)
    invoice_no = next_invoice_no(supplier, ground_truth_docs)
    ewb_no = next_ewb_no(ground_truth_docs, rng)
    ticket_no = next_ticket_no(processor["processor_id"], ground_truth_docs)
    to_pin = processor_pin_code(processor["processor_id"], ground_truth_docs)
    return build_demo_extra_shipment(
        processor, supplier, rng, as_of_month, invoice_no, ewb_no, ticket_no, to_pin, remark_hi
    )
