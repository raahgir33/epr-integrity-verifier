"""Per-processor monthly FY2025-26 material flow, per-document facts (with
printed + canonical values), and F1-F8/H1-H4 issue injection.

See docs/DATA_SPEC.md §3-§5 for the rules this encodes. FY2025-26 runs
April 2025 - March 2026, 12 months.
"""

import datetime
import math
import random

from scripts.dossier_gen.world import Processor, Supplier

FY_MONTHS = [
    "2025-04",
    "2025-05",
    "2025-06",
    "2025-07",
    "2025-08",
    "2025-09",
    "2025-10",
    "2025-11",
    "2025-12",
    "2026-01",
    "2026-02",
    "2026-03",
]

_HSN_WASTE = "3915"
_NORMAL_DESCRIPTIONS_EN = [
    "Post-consumer plastic waste, mixed PE/PP",
    "Segregated plastic scrap, LDPE film",
    "Baled plastic waste, HDPE",
]
_NORMAL_DESCRIPTIONS_HI = [
    "उपभोक्ता-पश्चात प्लास्टिक अपशिष्ट, मिश्रित पीई/पीपी",
]
_F8_DESCRIPTIONS_EN = ["Virgin LDPE granules", "Fresh film rolls, unused"]
_F8_DESCRIPTIONS_HI = ["प्राइम ग्रेड दाना"]


def pc(printed: str, canonical) -> dict:
    """A document field with both its printed form and canonical value."""
    return {"printed": printed, "canonical": canonical}


def format_indian_number(value: float, decimals: int = 2) -> str:
    sign = "-" if value < 0 else ""
    value = abs(value)
    int_part, _, frac_part = f"{value:.{decimals}f}".partition(".")
    if len(int_part) <= 3:
        grouped = int_part
    else:
        last3 = int_part[-3:]
        rest = int_part[:-3]
        parts = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        grouped = ",".join(parts) + "," + last3
    return f"{sign}{grouped}.{frac_part}" if decimals else f"{sign}{grouped}"


def fmt_date(d: datetime.date) -> str:
    return d.strftime("%d/%m/%Y")


def fmt_datetime(dt: datetime.datetime) -> str:
    return dt.strftime("%d-%m-%Y %H:%M")


def month_bounds(month: str) -> tuple[datetime.date, datetime.date]:
    year, mon = (int(x) for x in month.split("-"))
    start = datetime.date(year, mon, 1)
    end_month = mon + 1 if mon < 12 else 1
    end_year = year if mon < 12 else year + 1
    end = datetime.date(end_year, end_month, 1) - datetime.timedelta(days=1)
    return start, end


def months_elapsed(month: str) -> int:
    """1-indexed count of FY months up to and including `month`."""
    return FY_MONTHS.index(month) + 1


class Dossier:
    def __init__(self, processor_id: str):
        self.processor_id = processor_id
        self.documents: list[dict] = []
        self.shipments: list[dict] = []
        self.outputs: list[dict] = []
        self.energy_monthly: list[dict] = []
        self.certificates: list[dict] = []

    def add_document(self, doc_type: str, lang: str, fields: dict) -> str:
        doc_id = f"{self.processor_id}-{doc_type.upper()}-{len(self.documents) + 1:03d}"
        self.documents.append(
            {
                "doc_id": doc_id,
                "doc_type": doc_type,
                "processor_id": self.processor_id,
                "lang": lang,
                "fields": fields,
            }
        )
        return doc_id


def _monthly_certified_ratio(processor: Processor, month_index: int) -> float:
    """Fraction of monthly capacity certified for this processor/month, before
    the F1 override below."""
    if "H1" in processor.hard_negatives:
        return 0.95
    return 0.75


def _annual_inbound_target_t(processor: Processor) -> float:
    """Total FY inbound tonnage this processor should receive, so verified
    inbound tracks certified tonnes for clean processors regardless of how
    shipments happen to cluster by month. F1's inflated *certified* ratio is
    deliberately NOT used here — F1 is a paperwork/capacity issue, not backed
    by extra real inbound, so it isn't credited with extra verified tonnage."""
    ratio = 0.95 if "H1" in processor.hard_negatives else 0.75
    return processor.capacity_t_per_year * ratio


def build_dossier(
    processor: Processor,
    suppliers: list[Supplier],
    rng: random.Random,
    force_hindi: bool = False,
    f4_source: "Dossier | None" = None,
) -> Dossier:
    dossier = Dossier(processor.processor_id)
    is_recycler = processor.type == "recycler"
    # F1/F2/F3 are specifically seeded to create a certified-vs-verified
    # mismatch, so their certified tonnage (and, below, their electricity
    # use) stays on the old independent smooth-capacity-ratio basis. Every
    # other processor certifies on — and now also draws its electricity
    # use from — the month's actual verified weighbridge net, so the two
    # stay consistent with each other even though the generator spreads
    # real shipments unevenly across months (see docs/PROGRESS.md).
    _CERTIFIED_MISMATCH_ISSUES = {"F1", "F2", "F3"}
    honest_basis = not (_CERTIFIED_MISMATCH_ISSUES & set(processor.issue_types))

    # --- CTO and EPR registration certificates (facts already in `processor`) ---
    dossier.add_document(
        "cto",
        "en",
        {
            "consent_no": pc(processor.consent_no, processor.consent_no),
            "processor_name": pc(processor.name, processor.name),
            "address": pc(processor.address, processor.address),
            "permitted_categories": pc(
                ", ".join(processor.permitted_categories), list(processor.permitted_categories)
            ),
            "capacity_t_per_year": pc(
                format_indian_number(processor.capacity_t_per_year, 0),
                processor.capacity_t_per_year,
            ),
            "valid_from": pc(processor.consent_valid_from, processor.consent_valid_from),
            "valid_to": pc(processor.consent_valid_to, processor.consent_valid_to),
        },
    )
    dossier.add_document(
        "epr_registration",
        "en",
        {
            "registration_no": pc(processor.registration_no, processor.registration_no),
            "processor_type": pc(processor.type, processor.type),
            "categories": pc(
                ", ".join(processor.permitted_categories), list(processor.permitted_categories)
            ),
            "capacity_t_per_year": pc(
                format_indian_number(processor.capacity_t_per_year, 0),
                processor.capacity_t_per_year,
            ),
        },
    )

    # --- inbound shipments: invoice + e-way bill + weighbridge slip ---
    total_inbound = rng.randint(8, 14)
    month_for_shipment = [rng.choice(FY_MONTHS) for _ in range(total_inbound)]
    month_counts: dict[str, int] = {}
    for m in month_for_shipment:
        month_counts[m] = month_counts.get(m, 0) + 1

    # Special-case indices, chosen deterministically after the month layout exists.
    f3_index = 0 if "F3" in processor.issue_types else None
    f2_indices = {0, 1} if "F2" in processor.issue_types else set()
    f7_target_month = None
    if "F7" in processor.issue_types:
        f7_target_month = max(month_counts, key=lambda m: month_counts[m])
    h3_index = 0 if "H3" in processor.hard_negatives else None
    h2_index = 0 if "H2" in processor.hard_negatives else None
    f8_index = 0 if "F8" in processor.issue_types else None
    h4_month = None
    if "H4" in processor.hard_negatives:
        h4_month = FY_MONTHS[8]  # December 2025: a quiet shutdown month

    effective_inbound_count = total_inbound - month_counts.get(h4_month, 0)
    qty_per_shipment_baseline = _annual_inbound_target_t(processor) / max(
        effective_inbound_count, 1
    )

    seen_counts: dict[str, int] = {}
    for i, month in enumerate(month_for_shipment):
        seen_counts[month] = seen_counts.get(month, 0) + 1
        seq_in_month = seen_counts[month]
        if h4_month is not None and month == h4_month:
            continue  # no inbound during the planned shutdown month

        start, _end = month_bounds(month)
        day = rng.randint(1, 25)
        invoice_date = start + datetime.timedelta(days=day - 1)
        supplier = rng.choice(suppliers)

        lang = "hi" if (force_hindi and i == 0) else "en"
        is_f8 = i == f8_index
        if is_f8:
            # PWP-08 is the F8-only showcase processor — give it the Hindi
            # wording ("प्राइम ग्रेड दाना") so at least one F8 instance uses
            # it, independent of `force_hindi` (which only applies to the
            # PWP-01 sample, and PWP-01 never carries F8).
            use_hindi = processor.processor_id == "PWP-08"
            desc = (_F8_DESCRIPTIONS_HI if use_hindi else _F8_DESCRIPTIONS_EN)[0]
            lang = "hi" if use_hindi else "en"
        else:
            desc = (_NORMAL_DESCRIPTIONS_HI if lang == "hi" else _NORMAL_DESCRIPTIONS_EN)[0]

        qty_t = round(qty_per_shipment_baseline * rng.uniform(0.9, 1.1), 2)
        rate = round(rng.uniform(8, 18), 2)
        value = round(qty_t * 1000 * rate, 2)
        invoice_no = f"{processor.processor_id}-INV-{i + 1:03d}"

        invoice_doc_id = dossier.add_document(
            "inbound_invoice",
            lang,
            {
                "invoice_no": pc(invoice_no, invoice_no),
                "date": pc(fmt_date(invoice_date), invoice_date.isoformat()),
                "supplier_gstin": pc(supplier.gstin, supplier.gstin),
                "buyer_gstin": pc(processor.gstin, processor.gstin),
                "item_description": pc(desc, desc),
                "hsn": pc(_HSN_WASTE, _HSN_WASTE),
                "quantity_t": pc(format_indian_number(qty_t), qty_t),
                "rate": pc(format_indian_number(rate), rate),
                "value": pc(format_indian_number(value), value),
            },
        )

        distance_km = 900.0 if i == h2_index else round(rng.uniform(40, 300), 1)
        avg_speed = rng.uniform(30, 48)
        transit_hours = distance_km / avg_speed
        generated_at = datetime.datetime.combine(
            invoice_date, datetime.time(rng.randint(8, 11), rng.randint(0, 59))
        )
        weighbridge_in = generated_at + datetime.timedelta(hours=transit_hours)
        ewb_valid_days = -(-int(distance_km) // 200)  # ceil(distance / 200)
        valid_until = datetime.datetime.combine(
            generated_at.date() + datetime.timedelta(days=ewb_valid_days), datetime.time(23, 59, 59)
        )
        state_abbr = rng.choice(["MH", "GJ", "TN", "TG", "MP", "HR", "RJ"])
        vehicle_no = f"{state_abbr}{rng.randint(10, 59):02d}AB{rng.randint(1000, 9999)}"
        ewb_no = f"{rng.randint(10**10, 10**11 - 1)}"

        eway_doc_id = dossier.add_document(
            "eway_bill",
            lang,
            {
                "ewb_no": pc(ewb_no, ewb_no),
                "generated_at": pc(fmt_datetime(generated_at), generated_at.isoformat()),
                "valid_until": pc(fmt_datetime(valid_until), valid_until.isoformat()),
                "from_gstin": pc(supplier.gstin, supplier.gstin),
                "to_gstin": pc(processor.gstin, processor.gstin),
                "from_pin": pc(supplier.pin_code, supplier.pin_code),
                "to_pin": pc(
                    processor.address[-6:] if processor.address[-6:].isdigit() else "400001",
                    "400001",
                ),
                "distance_km": pc(f"{distance_km:.1f}", distance_km),
                "vehicle_no": pc(vehicle_no, vehicle_no),
                "hsn": pc(_HSN_WASTE, _HSN_WASTE),
                "quantity_t": pc(format_indian_number(qty_t), qty_t),
                "value": pc(format_indian_number(value), value),
                "invoice_no": pc(invoice_no, invoice_no),
            },
        )

        weighbridge_doc_id = None
        net_t = qty_t
        if i not in f2_indices:
            if i == f3_index:
                net_t = round(qty_t * 0.75, 2)
            elif i == h3_index:
                net_t = round(qty_t * 0.985, 2)
            else:
                # Strictly inside QTY_TOL_WEIGHBRIDGE (2%), with margin —
                # a clean shipment must never trip C4 by chance. Only F3
                # (-25%) and H3 (-1.5%, deliberately near the limit) exceed
                # this band, via their own branches above.
                net_t = round(qty_t * rng.uniform(0.988, 1.012), 2)
            gross_kg = round((net_t + rng.uniform(8, 15)) * 1000, 0)
            tare_kg = round(gross_kg - net_t * 1000, 0)
            ticket_no = f"{processor.processor_id}-WB-{i + 1:04d}"
            out_time = weighbridge_in + datetime.timedelta(minutes=rng.randint(15, 45))
            weighbridge_doc_id = dossier.add_document(
                "weighbridge_slip",
                lang,
                {
                    "ticket_no": pc(ticket_no, ticket_no),
                    "vehicle_no": pc(vehicle_no, vehicle_no),
                    "gross_kg": pc(format_indian_number(gross_kg, 0), gross_kg),
                    "tare_kg": pc(format_indian_number(tare_kg, 0), tare_kg),
                    "net_kg": pc(format_indian_number(net_t * 1000, 0), net_t * 1000),
                    "in_time": pc(fmt_datetime(weighbridge_in), weighbridge_in.isoformat()),
                    "out_time": pc(fmt_datetime(out_time), out_time.isoformat()),
                    "remarks": pc("", ""),
                },
            )

        dossier.shipments.append(
            {
                "shipment_id": f"{processor.processor_id}-SHP-{i + 1:03d}",
                "month": month,
                "invoice_doc_id": invoice_doc_id,
                "eway_doc_id": eway_doc_id,
                "weighbridge_doc_id": weighbridge_doc_id,
                "invoice_qty_t": qty_t,
                "weighbridge_net_t": net_t if weighbridge_doc_id else None,
                "match_status": "matched" if weighbridge_doc_id else "unmatched",
                "is_f8": is_f8,
                "ewb_no": ewb_no,
                "vehicle_no": vehicle_no,
                "distance_km": distance_km,
                "seq_in_month": seq_in_month,
                # Whether this shipment's tonnage counts toward verified
                # inbound tonnes (docs/DATA_SPEC.md §4a) — false for the F2
                # unmatched and F3 out-of-tolerance shortfall shipments.
                "verified": i not in f2_indices and i != f3_index,
            }
        )

    # --- F4: copy a record from f4_source (PWP-01) with no matching weighbridge slip ---
    if "F4" in processor.issue_types and f4_source is not None:
        original = f4_source.shipments[0]
        orig_invoice = next(
            d for d in f4_source.documents if d["doc_id"] == original["invoice_doc_id"]
        )
        orig_eway = next(d for d in f4_source.documents if d["doc_id"] == original["eway_doc_id"])

        dup_invoice_id = dossier.add_document("inbound_invoice", "en", dict(orig_invoice["fields"]))
        dup_eway_id = dossier.add_document("eway_bill", "en", dict(orig_eway["fields"]))
        dossier.shipments.append(
            {
                "shipment_id": f"{processor.processor_id}-SHP-DUP-001",
                "month": original["month"],
                "invoice_doc_id": dup_invoice_id,
                "eway_doc_id": dup_eway_id,
                "weighbridge_doc_id": None,
                "invoice_qty_t": original["invoice_qty_t"],
                "weighbridge_net_t": None,
                "match_status": "unmatched",
                "is_f8": False,
                "ewb_no": original["ewb_no"],
                "duplicate_of": original["shipment_id"],
                "duplicate_of_processor": f4_source.processor_id,
                "verified": False,
            }
        )

    # --- outbound sales invoices (recyclers only — no recycled product for end-of-life) ---
    if is_recycler:
        matched_total = sum(s["weighbridge_net_t"] or 0 for s in dossier.shipments)
        n_out = rng.randint(4, 8)
        out_month_pool = [m for m in FY_MONTHS if m != h4_month]
        for j in range(n_out):
            month = rng.choice(out_month_pool)
            start, _end = month_bounds(month)
            out_date = start + datetime.timedelta(days=rng.randint(1, 25))
            qty = round((matched_total * 0.8 / max(n_out, 1)) * rng.uniform(0.85, 1.15), 2)
            doc_id = dossier.add_document(
                "outbound_invoice",
                "en",
                {
                    "invoice_no": pc(
                        f"{processor.processor_id}-OUT-{j + 1:03d}",
                        f"{processor.processor_id}-OUT-{j + 1:03d}",
                    ),
                    "date": pc(fmt_date(out_date), out_date.isoformat()),
                    "buyer": pc(f"Fictional Buyer {j + 1}", f"Fictional Buyer {j + 1}"),
                    "item_description": pc("Recycled PE/PP granules", "Recycled PE/PP granules"),
                    "hsn": pc("3915", "3915"),
                    "quantity_t": pc(format_indian_number(qty), qty),
                },
            )
            dossier.outputs.append({"doc_id": doc_id, "month": month, "quantity_t": qty})

    # --- electricity bills, monthly ---
    # honest_basis processors: tied to that month's actual verified
    # weighbridge net, the same figure now driving their certificates —
    # kwh and certified move together, so a month with few/no shipments
    # (there are only 8-14 spread over 12 months) is skipped by
    # checks/energy.py's zero-certified guard rather than mismatching
    # against a kwh figure drawn from an unrelated smooth target.
    # F1/F2/F3 processors keep the old independent smooth-capacity-ratio
    # basis (unchanged), consistent with their certified tonnage.
    connected_load_kw = round(processor.capacity_t_per_year / 10, 1)
    for month in FY_MONTHS:
        if honest_basis:
            monthly_basis_t = sum(
                s["weighbridge_net_t"]
                for s in dossier.shipments
                if s["month"] == month and s["verified"]
            )
        else:
            ratio = _monthly_certified_ratio(processor, FY_MONTHS.index(month))
            if "F1" in processor.issue_types:
                ratio = 1.3
            monthly_basis_t = processor.capacity_t_per_year / 12 * ratio
        if month == h4_month:
            kwh = round(rng.uniform(10, 40), 1)
        elif month == f7_target_month:
            kwh = round(rng.uniform(5, 30), 1)
        else:
            kwh_per_t = rng.uniform(350, 500)
            kwh = round(monthly_basis_t * kwh_per_t, 1)
        doc_id = dossier.add_document(
            "electricity_bill",
            "en",
            {
                "billing_month": pc(month, month),
                "units_consumed_kwh": pc(format_indian_number(kwh), kwh),
                "connected_load_kw": pc(format_indian_number(connected_load_kw), connected_load_kw),
            },
        )
        dossier.energy_monthly.append({"doc_id": doc_id, "month": month, "kwh": kwh})

    # --- certificates: one per month, category from permitted set (F6: one breach) ---
    # honest_basis processors certify on the month's actual verified
    # weighbridge net, rounded down — honest practice, and (together with
    # the matching electricity-use basis above) it removes the
    # noise-driven false C2a/C7 failures an independently-drawn target
    # could otherwise produce purely by chance (docs/PROGRESS.md has the
    # before/after sweep). F1/F2/F3 processors keep the old independent
    # smooth-capacity-ratio basis, since their whole premise is a
    # certified-vs-verified mismatch (F1 against capacity; F2/F3 against
    # verified inbound).
    monthly_certified_t: dict[str, float] = {}
    for month in FY_MONTHS:
        if honest_basis:
            verified_month_t = sum(
                s["weighbridge_net_t"]
                for s in dossier.shipments
                if s["month"] == month and s["verified"]
            )
            monthly_certified_t[month] = math.floor(verified_month_t * 100) / 100
        else:
            ratio = _monthly_certified_ratio(processor, FY_MONTHS.index(month))
            if "F1" in processor.issue_types:
                ratio = 1.3
            if month == h4_month:
                ratio = 0.0
            monthly_capacity = processor.capacity_t_per_year / 12
            monthly_certified_t[month] = round(monthly_capacity * ratio, 2)

    # F6's category breach must land on a month with real tonnage, or the
    # breach is a no-op — under honest_basis, an early FY month can
    # legitimately have zero shipments by chance (unlike the old smooth
    # formula, which gave every month the same non-zero share).
    f6_month = None
    if "F6" in processor.issue_types:
        f6_month = next((m for m in FY_MONTHS if monthly_certified_t[m] > 0), FY_MONTHS[0])

    for month in FY_MONTHS:
        category = processor.permitted_categories[0]
        if month == f6_month:
            category = "I" if "I" not in processor.permitted_categories else "III"
        dossier.certificates.append(
            {
                "certificate_id": f"CERT-{processor.processor_id}-{month}",
                "category": category,
                "quantity_t": monthly_certified_t[month],
                "generation_date": fmt_date(month_bounds(month)[1]),
                "period_month": month,
            }
        )

    return dossier
