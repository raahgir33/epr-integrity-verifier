"""Per-processor monthly FY2025-26 material flow, per-document facts (with
printed + canonical values), and F1-F8/H1-H4 issue injection.

See docs/DATA_SPEC.md §3-§5 for the rules this encodes. FY2025-26 runs
April 2025 - March 2026, 12 months.
"""

import datetime
import math
import random

from app.checks import params
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
# Category I/II (rigid/flexible) wording — recyclers (permitted_categories
# includes "I" or "II").
_NORMAL_DESCRIPTIONS_EN = [
    "Post-consumer plastic waste, mixed PE/PP",
    "Segregated plastic scrap, LDPE film",
    "Baled plastic waste, HDPE",
]
_NORMAL_DESCRIPTIONS_HI = [
    "उपभोक्ता-पश्चात प्लास्टिक अपशिष्ट, मिश्रित पीई/पीपी",
]
# Category III/IV (multilayered/compostable) wording — end-of-life
# processors (permitted_categories is ["III", "IV"]). Same HSN 3915
# (waste/scrap) — only the category changes, not the HSN chapter. Fixes a
# universal, unintentional category mismatch found during the T10 realism
# investigation: every PWP-09/PWP-10 shipment previously used the
# recycler-oriented wording above regardless of what the processor was
# actually permitted to handle (docs/PROGRESS.md).
_EOL_DESCRIPTIONS_EN = [
    "Multilayered plastic pouches and sachets, mixed",
    "Baled multilayer packaging waste",
    "Compostable plastic sheet waste, mixed",
]
_EOL_DESCRIPTIONS_HI = [
    "बहुस्तरीय प्लास्टिक पाउच और पाउच अपशिष्ट, मिश्रित",
]
_F8_DESCRIPTIONS_EN = ["Virgin LDPE granules", "Fresh film rolls, unused"]
_F8_DESCRIPTIONS_HI = ["प्राइम ग्रेड दाना"]

# Vehicle classes (ASSUMPTION: approximate Indian commercial goods-vehicle
# GVW/payload bands for scrap/waste road transport — not cited to a
# specific dated regulatory source, since legal GVW limits are tiered by
# axle count and periodically revised. Chosen so net+tare never exceeds a
# plausible GVW for that class; see docs/PROGRESS.md and
# tests/test_generator_realism.py, which enforces this on every clean/
# hard-negative shipment.)
_VEHICLE_CLASSES = {
    "light_2axle": {"net_t": (7.0, 9.0), "tare_kg": (4000, 6000)},
    "heavy_multiaxle": {"net_t": (15.0, 25.0), "tare_kg": (7000, 10000)},
}
_LIGHT_AVG_NET_T = sum(_VEHICLE_CLASSES["light_2axle"]["net_t"]) / 2
_HEAVY_AVG_NET_T = sum(_VEHICLE_CLASSES["heavy_multiaxle"]["net_t"]) / 2
_MIN_SHIPMENTS = 15
_MAX_SHIPMENTS = 25


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km (mean Earth radius 6371 km)."""
    earth_radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * earth_radius_km * math.asin(math.sqrt(a))


_TARGET_MARGIN = 0.75  # see _shipment_plan's docstring


def _shipment_plan(target_annual_t: float, rng: random.Random) -> tuple[int, float]:
    """Returns (shipment_count, heavy_class_fraction), sized together so
    the realistic total lands at roughly _TARGET_MARGIN of
    target_annual_t on average — not 100%, since per-shipment draws have
    variance and C1 requires certified_t (honest-basis: derived FROM the
    actual total) to never exceed capacity x ratio; aiming for the
    ceiling itself would let upside variance tip a clean processor over
    it by chance.

    Shipment count and class mix are solved together, not independently
    (confirmed necessary empirically, docs/PROGRESS.md): starting from an
    all-light assumption keeps a small processor's count naturally low
    rather than forcing extra shipments a small target can't support
    without either exceeding the ceiling or needing an artificially thin
    heavy-class sliver whose own wide range (15-25 t) would otherwise
    dominate that processor's total variance.
    """
    target = target_annual_t * _TARGET_MARGIN
    base_n = target / _LIGHT_AVG_NET_T
    n = max(_MIN_SHIPMENTS, min(_MAX_SHIPMENTS, round(base_n)))
    n = max(1, n + rng.randint(-1, 1))
    avg_net_needed = target / n
    p_heavy = (avg_net_needed - _LIGHT_AVG_NET_T) / (_HEAVY_AVG_NET_T - _LIGHT_AVG_NET_T)
    return n, min(0.95, max(0.0, p_heavy))


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
    total_inbound, p_heavy = _shipment_plan(_annual_inbound_target_t(processor), rng)
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

    # H2 (long-haul, ~900 km) gets a specific real supplier (Alwar) whose
    # great-circle distance to this processor's site, times ROAD_FACTOR,
    # already lands close to 900 km — so H2's declared distance is
    # geographically consistent rather than a bare magic number (T10
    # realism fix, docs/PROGRESS.md). Falls back to a random supplier if
    # this seed's supplier list is ever rebuilt without an Alwar entry.
    h2_supplier = next((s for s in suppliers if s.city == "Alwar"), None)

    # Every other (non-H2) shipment draws from same-state suppliers only
    # — real waste aggregators are regional, and a nationwide-random
    # supplier pool combined with a real haversine distance (below) would
    # otherwise produce absurd long-haul "normal" shipments (confirmed:
    # up to ~2,700 km before this restriction) that aren't part of any
    # seeded issue. H2 is the sole deliberate long-haul exception.
    #
    # Also excludes suppliers implausibly close to this processor's own
    # site (< _MIN_SUPPLIER_DISTANCE_KM raw great-circle) — not a
    # geography concern, a printed-timestamp-precision one: e-way-bill/
    # weighbridge times are printed to the minute (docs/DATA_SPEC.md §3),
    # so a transit of only a couple of minutes lets ±1 minute of print
    # rounding swing the *recomputed* speed past MAX_AVG_SPEED_KMPH even
    # though the real (canonical, sub-minute) speed never does — confirmed
    # empirically (seed 4/PWP-10/SHP-004, a 2.3 km hop). The original
    # pre-fix design had a 40 km floor for exactly this reason; this
    # keeps that safety margin while staying geographically real (filters
    # suppliers, never fakes the distance of the one actually chosen).
    _MIN_SUPPLIER_DISTANCE_KM = 25.0
    same_state_suppliers = (
        [
            s
            for s in suppliers
            if s.state == processor.state
            and haversine_km(s.lat, s.lon, processor.lat, processor.lon)
            >= _MIN_SUPPLIER_DISTANCE_KM
        ]
        or [s for s in suppliers if s.state == processor.state]
        or suppliers
    )

    # Tracks (weighbridge_in, weighbridge_doc) for every matched shipment
    # so ticket_no can be finalized chronologically after this loop (one
    # physical weighbridge per site — T10 realism fix, docs/PROGRESS.md),
    # since shipments are generated in random month order, not date order.
    weighbridge_entries: list[tuple[datetime.datetime, dict]] = []

    seen_counts: dict[str, int] = {}
    for i, month in enumerate(month_for_shipment):
        seen_counts[month] = seen_counts.get(month, 0) + 1
        seq_in_month = seen_counts[month]
        if h4_month is not None and month == h4_month:
            continue  # no inbound during the planned shutdown month

        start, _end = month_bounds(month)
        day = rng.randint(1, 25)
        invoice_date = start + datetime.timedelta(days=day - 1)
        if h2_index is not None and i == h2_index and h2_supplier is not None:
            supplier = h2_supplier
        else:
            supplier = rng.choice(same_state_suppliers)

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
        elif is_recycler:
            desc = (_NORMAL_DESCRIPTIONS_HI if lang == "hi" else _NORMAL_DESCRIPTIONS_EN)[0]
        else:
            # End-of-life processor (permitted categories III/IV) — fixes
            # a universal, unintentional category mismatch (every
            # shipment previously used recycler-oriented I/II wording
            # regardless of what this processor is actually permitted to
            # handle; docs/PROGRESS.md). F6's own deliberate one-month
            # certificate-level category breach, below, is unaffected.
            desc = (_EOL_DESCRIPTIONS_HI if lang == "hi" else _EOL_DESCRIPTIONS_EN)[0]

        vehicle_class = "heavy_multiaxle" if rng.random() < p_heavy else "light_2axle"
        net_t_range = _VEHICLE_CLASSES[vehicle_class]["net_t"]
        qty_t = round(rng.uniform(*net_t_range), 2)
        # ASSUMPTION: ₹/kg for mixed post-consumer plastic scrap — not
        # cited to a specific source (docs/DATA_SPEC.md §1 has no entry
        # for scrap pricing). Verified to always clear the ₹50,000
        # e-way-bill threshold even at the smallest realistic shipment
        # (7 t x Rs 8/kg = Rs 56,000) — see tests/test_generator_realism.py.
        rate = round(rng.uniform(8, 18), 2)
        value = round(qty_t * 1000 * rate, 2)
        # Placeholder — finalized by assign_cross_processor_identifiers()
        # after every processor's dossier exists (the real series is
        # per-SUPPLIER, chronological by date, and suppliers are shared
        # across processors; T10 realism fix, docs/PROGRESS.md).
        invoice_no = ""

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

        raw_km = haversine_km(supplier.lat, supplier.lon, processor.lat, processor.lon)
        distance_km = round(raw_km * params.ROAD_FACTOR * rng.uniform(0.95, 1.1), 1)
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
        # Placeholder — finalized by assign_cross_processor_identifiers()
        # (GSTN issues e-way bill numbers from one central, roughly
        # time-ordered sequence, not per-supplier/processor; T10 realism
        # fix, docs/PROGRESS.md).
        ewb_no = ""

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
                "to_pin": pc(processor.pin_code, processor.pin_code),
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
            # Tare drawn independently from the SAME vehicle class as the
            # invoice quantity (not derived from net_t) — physically
            # correct (gross is definitionally net+tare) and realistic at
            # any shipment size, replacing the pre-fix formula that added
            # 8-15 TONNES of "tare" regardless of net_t (plausible only
            # when net_t was ~500 t; absurd at a realistic ~8-25 t net).
            tare_kg = round(rng.uniform(*_VEHICLE_CLASSES[vehicle_class]["tare_kg"]), 0)
            net_kg = net_t * 1000
            gross_kg = net_kg + tare_kg
            out_time = weighbridge_in + datetime.timedelta(minutes=rng.randint(15, 45))
            weighbridge_doc_id = dossier.add_document(
                "weighbridge_slip",
                lang,
                {
                    # ticket_no finalized chronologically after this loop
                    # (same weighbridge_entries pass below) — placeholder
                    # here is never read, just keeps the field present.
                    "ticket_no": pc("", ""),
                    "vehicle_no": pc(vehicle_no, vehicle_no),
                    "gross_kg": pc(format_indian_number(gross_kg, 0), gross_kg),
                    "tare_kg": pc(format_indian_number(tare_kg, 0), tare_kg),
                    "net_kg": pc(format_indian_number(net_kg, 0), net_kg),
                    "in_time": pc(fmt_datetime(weighbridge_in), weighbridge_in.isoformat()),
                    "out_time": pc(fmt_datetime(out_time), out_time.isoformat()),
                    "remarks": pc("", ""),
                },
            )
            weighbridge_entries.append(
                (weighbridge_in, dossier.documents[-1])  # the doc just added, for in-place rewrite
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

    # Finalize weighbridge ticket numbers chronologically by actual
    # in_time (one physical weighbridge per site — T10 realism fix,
    # docs/PROGRESS.md) — the main loop above builds shipments in random
    # month order, not date order, so this can only be assigned after.
    weighbridge_entries.sort(key=lambda t: t[0])
    for seq, (_in_time, doc) in enumerate(weighbridge_entries, start=1):
        ticket_no = f"{processor.weighbridge_code}-{seq:05d}"
        doc["fields"]["ticket_no"] = pc(ticket_no, ticket_no)

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
        # Dates drawn first and sorted before building documents, so the
        # processor's own invoice series (T10 realism fix — the
        # processor's own prefix, never the internal processor_id) comes
        # out chronological, not in random draw order.
        out_dates = []
        for _j in range(n_out):
            month = rng.choice(out_month_pool)
            start, _end = month_bounds(month)
            out_date = start + datetime.timedelta(days=rng.randint(1, 25))
            out_dates.append((out_date, month))
        out_dates.sort(key=lambda t: t[0])
        for seq, (out_date, month) in enumerate(out_dates, start=1):
            qty = round((matched_total * 0.8 / max(n_out, 1)) * rng.uniform(0.85, 1.15), 2)
            invoice_no = f"{processor.invoice_prefix}/25-26/{seq:04d}"
            doc_id = dossier.add_document(
                "outbound_invoice",
                "en",
                {
                    "invoice_no": pc(invoice_no, invoice_no),
                    "date": pc(fmt_date(out_date), out_date.isoformat()),
                    "buyer": pc(f"Fictional Buyer {seq}", f"Fictional Buyer {seq}"),
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
    # One consumer/account number per processor (not per bill — it's a
    # DISCOM account identifier, the same across all 12 monthly bills),
    # plausible all-numeric format, never the internal processor_id (T10
    # realism fix, docs/PROGRESS.md).
    consumer_no = f"{rng.randint(10**9, 10**10 - 1)}"
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
            # T10 realism fix (docs/PROGRESS.md): tied to the same
            # monthly_basis_t every other month uses, at a much lower but
            # still-plausible ratio — not an absolute number decoupled
            # from this processor's own scale (the original 5-30 kWh flat
            # draw read as implausible rather than just "low" once
            # per-shipment tonnage became realistic). Still comfortably
            # below KWH_PER_T_MIN, so C7 still fails.
            kwh = round(
                monthly_basis_t * rng.uniform(params.F7_KWH_PER_T_MIN, params.F7_KWH_PER_T_MAX), 1
            )
        else:
            kwh_per_t = rng.uniform(350, 500)
            kwh = round(monthly_basis_t * kwh_per_t, 1)
        doc_id = dossier.add_document(
            "electricity_bill",
            "en",
            {
                "consumer_no": pc(consumer_no, consumer_no),
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

    # T10 realism fix: a generic portal-reference-style serial, anchored
    # on this processor's own registration number suffix (already a
    # per-processor-unique random reference) rather than the internal
    # processor_id — keeps certificate_id globally unique across
    # processors without reintroducing the same bug (certificates are a
    # structured ledger, not an extracted document — DATA_SPEC.md §3 —
    # but dropping the internal id keeps it consistent with every other
    # identifier fix, docs/PROGRESS.md).
    registration_suffix = processor.registration_no.rsplit("/", 1)[-1]
    for month in FY_MONTHS:
        category = processor.permitted_categories[0]
        if month == f6_month:
            category = "I" if "I" not in processor.permitted_categories else "III"
        dossier.certificates.append(
            {
                "certificate_id": f"EPR-CERT/{registration_suffix}/{month.replace('-', '')}",
                "category": category,
                "quantity_t": monthly_certified_t[month],
                "generation_date": fmt_date(month_bounds(month)[1]),
                "period_month": month,
            }
        )

    return dossier


def assign_cross_processor_identifiers(
    dossiers: dict[str, "Dossier"], suppliers: list[Supplier], rng: random.Random
) -> None:
    """Finalizes invoice_no (per supplier, monotonic with invoice date)
    and ewb_no (one global sequence, monotonic with generation time) once
    every processor's dossier exists — both span suppliers/processors
    shared across dossiers, which build_dossier() can't see on its own
    (T10 realism fix, docs/PROGRESS.md). Called once, after every real
    `build_dossier()` call (including any F4 duplicate) — the duplicate's
    copied fields are synced to its original's final values afterward,
    since a duplicate must stay an exact match of the original it copies,
    not the placeholder it happened to be built with.

    Mutates each dossier's documents (and, for ewb_no, each shipment dict
    too — app/checks/duplicates.py's C5 key reads shipment["ewb_no"]
    directly, not the document, so it must be kept in sync) in place.
    """
    supplier_by_gstin = {s.gstin: s for s in suppliers}
    supplier_by_id = {s.supplier_id: s for s in suppliers}

    # One pass to classify every shipment as "real" (gets a final series
    # position) or "duplicate" (synced to its original afterward), and to
    # build a (processor_id, shipment_id) -> (invoice_doc, eway_doc, shipment)
    # lookup every duplicate can resolve its original through.
    lookup: dict[tuple[str, str], tuple[dict, dict | None, dict]] = {}
    real_entries: list[tuple[dict, dict | None, dict]] = []  # (invoice_doc, eway_doc, shipment)
    duplicate_entries: list[tuple[dict, dict | None, dict, str, str]] = []
    for dossier in dossiers.values():
        docs_by_id = {d["doc_id"]: d for d in dossier.documents}
        for shipment in dossier.shipments:
            invoice_doc = docs_by_id[shipment["invoice_doc_id"]]
            eway_doc_id = shipment.get("eway_doc_id")
            eway_doc = docs_by_id.get(eway_doc_id) if eway_doc_id else None
            lookup[(dossier.processor_id, shipment["shipment_id"])] = (
                invoice_doc,
                eway_doc,
                shipment,
            )
            if "duplicate_of" in shipment:
                duplicate_entries.append(
                    (
                        invoice_doc,
                        eway_doc,
                        shipment,
                        shipment["duplicate_of"],
                        shipment["duplicate_of_processor"],
                    )
                )
            else:
                real_entries.append((invoice_doc, eway_doc, shipment))

    # --- Per-supplier invoice series, monotonic by invoice date ---
    by_supplier: dict[str, list[tuple[str, dict, dict | None]]] = {}
    for invoice_doc, eway_doc, _shipment in real_entries:
        supplier_gstin = invoice_doc["fields"]["supplier_gstin"]["canonical"]
        supplier_id = supplier_by_gstin[supplier_gstin].supplier_id
        date_str = invoice_doc["fields"]["date"]["canonical"]
        by_supplier.setdefault(supplier_id, []).append((date_str, invoice_doc, eway_doc))
    for supplier_id, items in by_supplier.items():
        items.sort(key=lambda t: t[0])
        prefix = supplier_by_id[supplier_id].invoice_prefix
        for seq, (_date_str, invoice_doc, eway_doc) in enumerate(items, start=1):
            new_no = f"{prefix}/25-26/{seq:04d}"
            invoice_doc["fields"]["invoice_no"] = pc(new_no, new_no)
            if eway_doc is not None:
                eway_doc["fields"]["invoice_no"] = pc(new_no, new_no)

    # --- Global e-way bill series, 12 digits, monotonic with generation time ---
    eway_entries = [
        (eway_doc["fields"]["generated_at"]["canonical"], eway_doc, shipment)
        for _invoice_doc, eway_doc, shipment in real_entries
        if eway_doc is not None
    ]
    eway_entries.sort(key=lambda t: t[0])
    current = rng.randint(10**11, 10**12 - 1 - 10_000_000)  # headroom for every increment below
    for _generated_at, eway_doc, shipment in eway_entries:
        current += rng.randint(100, 5000)
        ewb_no = str(current)
        eway_doc["fields"]["ewb_no"] = pc(ewb_no, ewb_no)
        shipment["ewb_no"] = ewb_no

    # --- Sync F4 duplicates to their (now-finalized) original ---
    for (
        dup_invoice_doc,
        dup_eway_doc,
        dup_shipment,
        orig_shipment_id,
        orig_processor_id,
    ) in duplicate_entries:
        orig_invoice_doc, orig_eway_doc, _orig_shipment = lookup[
            (orig_processor_id, orig_shipment_id)
        ]
        dup_invoice_doc["fields"]["invoice_no"] = dict(orig_invoice_doc["fields"]["invoice_no"])
        if dup_eway_doc is not None and orig_eway_doc is not None:
            dup_eway_doc["fields"]["invoice_no"] = dict(orig_eway_doc["fields"]["invoice_no"])
            dup_eway_doc["fields"]["ewb_no"] = dict(orig_eway_doc["fields"]["ewb_no"])
            dup_shipment["ewb_no"] = orig_eway_doc["fields"]["ewb_no"]["canonical"]
