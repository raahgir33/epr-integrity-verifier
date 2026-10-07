"""Realism validator for the T10 synthetic-data fix (docs/PROGRESS.md):
every clean or hard-negative (H1-H4) shipment must be physically and
geographically plausible — not just internally consistent with its own
seeded issue. Only F2/F3/F8/F4-duplicate shipments (deliberately
divergent by design) are excluded.

Seeds 1-20, excluding 7 (the held-out test set — never generated or
inspected here, directly or indirectly), same convention as
test_c2a_noise_robustness.py / test_f5_site_coordinate_coupling.py.
"""

import datetime
import re

import pytest

from app.checks import params
from scripts.dossier_gen.shipments import (
    _VEHICLE_CLASSES,
    haversine_km,
)
from scripts.dossier_gen.world import _CITY_FOR_PROCESSOR, PIN_PREFIX, STATE_GSTIN_CODE
from scripts.generate_dossiers import run_data_pipeline

DEV_SEEDS = [s for s in range(1, 21) if s != 7]
_EWAY_THRESHOLD_INR = 50_000
_DISTANCE_ROAD_FACTOR_JITTER = (0.95, 1.1)
_DISTANCE_TOLERANCE_KM = 1.0  # rounding slack on top of the jitter band


def _is_deliberately_divergent(shipment: dict) -> bool:
    """F2 (phantom/unmatched) and F3 (quantity inflation) both clear
    "verified": False; F4's duplicate has no "verified" key at all but
    carries "duplicate_of" instead; F8 only changes wording (not any
    field this validator checks) but is excluded anyway, per the
    approved plan."""
    if "duplicate_of" in shipment:
        return True
    if shipment.get("is_f8"):
        return True
    return not shipment.get("verified", True)


def _vehicle_class_for(net_t: float) -> str | None:
    """A matched shipment's weighbridge net_t is the invoice quantity
    (drawn from a vehicle class's net_t range) times a small noise
    multiplier (0.988-1.012 normally, 0.985 for H3) — so the realized
    net_t can land slightly outside the class's own boundary. A qty_t
    drawn at the heavy class's own ceiling (25.0) times the max noise
    multiplier (1.012) gives net_t=25.3, so the tolerance must cover at
    least 0.3 t on the upper side (seeds 15/20 hit exactly this)."""
    tolerance_t = 0.3
    for name, spec in _VEHICLE_CLASSES.items():
        low, high = spec["net_t"]
        if low - tolerance_t <= net_t <= high + tolerance_t:
            return name
    return None


def _parse_printed_datetime(printed: str) -> datetime.datetime:
    return datetime.datetime.strptime(printed, "%d-%m-%Y %H:%M")


def _parse_printed_date(printed: str) -> datetime.date:
    return datetime.datetime.strptime(printed, "%d/%m/%Y").date()


@pytest.mark.parametrize("seed", DEV_SEEDS)
def test_every_clean_and_hard_negative_shipment_is_realistic(seed):
    pipeline = run_data_pipeline(seed)
    suppliers_by_gstin = {s.gstin: s for s in pipeline["suppliers"]}

    checked = 0
    for processor in pipeline["processors"]:
        dossier = pipeline["dossiers"][processor.processor_id]
        docs_by_id = {d["doc_id"]: d for d in dossier.documents}

        # Processor-level GSTIN/PIN consistency (checked once per processor,
        # not per shipment).
        assert processor.gstin[:2] == STATE_GSTIN_CODE[processor.state], (
            f"seed {seed}/{processor.processor_id}: processor GSTIN state code "
            f"{processor.gstin[:2]!r} doesn't match its real state {processor.state!r}"
        )
        assert processor.pin_code[:3] == PIN_PREFIX[_CITY_FOR_PROCESSOR[processor.processor_id]], (
            f"seed {seed}/{processor.processor_id}: processor PIN {processor.pin_code!r} "
            "doesn't match its real city's prefix"
        )

        for shipment in dossier.shipments:
            if _is_deliberately_divergent(shipment):
                continue
            checked += 1
            sid = shipment["shipment_id"]
            invoice = docs_by_id[shipment["invoice_doc_id"]]
            eway = docs_by_id[shipment["eway_doc_id"]]
            weighbridge = docs_by_id.get(shipment["weighbridge_doc_id"] or "")

            # --- GSTIN / PIN consistency (supplier side) ---
            supplier_gstin = invoice["fields"]["supplier_gstin"]["canonical"]
            supplier = suppliers_by_gstin.get(supplier_gstin)
            assert supplier is not None, f"seed {seed}/{sid}: supplier GSTIN not found in roster"
            assert supplier.gstin[:2] == STATE_GSTIN_CODE[supplier.state], (
                f"seed {seed}/{sid}: supplier GSTIN state code doesn't match its real state"
            )
            from_pin = eway["fields"]["from_pin"]["canonical"]
            assert from_pin[:3] == PIN_PREFIX[supplier.city], (
                f"seed {seed}/{sid}: supplier PIN {from_pin!r} doesn't match {supplier.city!r}"
            )
            to_pin = eway["fields"]["to_pin"]["canonical"]
            assert to_pin == processor.pin_code, (
                f"seed {seed}/{sid}: e-way bill to_pin doesn't match the processor's own PIN"
            )

            # --- distance vs real great-circle x ROAD_FACTOR ---
            distance_km = eway["fields"]["distance_km"]["canonical"]
            raw_km = haversine_km(supplier.lat, supplier.lon, processor.lat, processor.lon)
            base_km = raw_km * params.ROAD_FACTOR
            low = base_km * _DISTANCE_ROAD_FACTOR_JITTER[0] - _DISTANCE_TOLERANCE_KM
            high = base_km * _DISTANCE_ROAD_FACTOR_JITTER[1] + _DISTANCE_TOLERANCE_KM
            assert low <= distance_km <= high, (
                f"seed {seed}/{sid}: distance_km={distance_km} outside the plausible "
                f"[{low:.1f}, {high:.1f}] band for raw great-circle {raw_km:.1f} km"
            )

            # --- implied transit speed ---
            generated_at = _parse_printed_datetime(eway["fields"]["generated_at"]["printed"])
            if weighbridge is not None:
                in_time = _parse_printed_datetime(weighbridge["fields"]["in_time"]["printed"])
                transit_hours = (in_time - generated_at).total_seconds() / 3600.0
                assert transit_hours > 0, f"seed {seed}/{sid}: non-positive transit time"
                implied_speed = distance_km / transit_hours
                assert implied_speed <= params.MAX_AVG_SPEED_KMPH, (
                    f"seed {seed}/{sid}: implied transit speed {implied_speed:.1f} km/h "
                    f"exceeds {params.MAX_AVG_SPEED_KMPH}"
                )

                # --- weighbridge GVW within its vehicle class's ceiling ---
                net_t = weighbridge["fields"]["net_kg"]["canonical"] / 1000.0
                vehicle_class = _vehicle_class_for(net_t)
                assert vehicle_class is not None, (
                    f"seed {seed}/{sid}: net_t={net_t} doesn't fall within any vehicle class"
                )
                gross_kg = weighbridge["fields"]["gross_kg"]["canonical"]
                tare_kg = weighbridge["fields"]["tare_kg"]["canonical"]
                net_kg = weighbridge["fields"]["net_kg"]["canonical"]
                assert gross_kg == pytest.approx(net_kg + tare_kg, abs=1.0), (
                    f"seed {seed}/{sid}: gross != net + tare"
                )
                _, net_high = _VEHICLE_CLASSES[vehicle_class]["net_t"]
                _, tare_high = _VEHICLE_CLASSES[vehicle_class]["tare_kg"]
                max_gvw = net_high * 1000 + tare_high
                assert gross_kg <= max_gvw, (
                    f"seed {seed}/{sid}: gross_kg={gross_kg} exceeds {vehicle_class}'s "
                    f"legal GVW ceiling {max_gvw}"
                )

                # --- dates ordered: invoice <= e-way generated_at <= weighbridge in_time ---
                invoice_date = _parse_printed_date(invoice["fields"]["date"]["printed"])
                assert invoice_date <= generated_at.date(), (
                    f"seed {seed}/{sid}: invoice date after e-way bill generation"
                )
                assert generated_at <= in_time, (
                    f"seed {seed}/{sid}: e-way bill generated after weighbridge in-time"
                )

            # --- invoice value == quantity_t * 1000 * rate ---
            qty_t = invoice["fields"]["quantity_t"]["canonical"]
            rate = invoice["fields"]["rate"]["canonical"]
            value = invoice["fields"]["value"]["canonical"]
            assert value == pytest.approx(qty_t * 1000 * rate, rel=1e-6), (
                f"seed {seed}/{sid}: invoice value doesn't equal quantity x rate"
            )

            # --- e-way bill present wherever value exceeds the GST threshold ---
            if value > _EWAY_THRESHOLD_INR:
                assert shipment.get("eway_doc_id"), (
                    f"seed {seed}/{sid}: value {value} exceeds the e-way-bill threshold "
                    "but no e-way bill is present"
                )

    assert checked > 0, "no shipments were actually checked — test would be vacuous"


_SUPPLIER_INVOICE_NO_RE = re.compile(r"^[A-Z0-9]+/25-26/\d{4}$")
_EWB_NO_RE = re.compile(r"^\d{12}$")
_CONSENT_NO_RE = re.compile(r"^CTO/[A-Z]{2}/\d{6}$")
_REGISTRATION_NO_RE = re.compile(r"^EPR-REG/[A-Z]{2}/\d{6}$")
_TICKET_NO_RE = re.compile(r"^[A-Z]{2}-WB-\d{4}-\d{5}$")
_CERTIFICATE_ID_RE = re.compile(r"^EPR-CERT/\d{6}/\d{6}$")
_CONSUMER_NO_RE = re.compile(r"^\d{10}$")


def _invoice_seq(invoice_no: str) -> int:
    return int(invoice_no.rsplit("/", 1)[-1])


@pytest.mark.parametrize("seed", DEV_SEEDS)
def test_document_identifiers_are_realistic(seed):
    """Every printed identifier (T10 realism fix, docs/PROGRESS.md): a
    real issuer-based format, no internal id substrings, and — for
    per-issuer series (supplier invoice numbers, the national e-way-bill
    sequence, a processor's own weighbridge tickets and output invoices)
    — strictly chronological. F4's duplicate shipment is excluded from
    the series checks: it deliberately copies its original's identifiers
    verbatim rather than taking its own sequence position."""
    pipeline = run_data_pipeline(seed)
    processors = pipeline["processors"]
    suppliers = pipeline["suppliers"]
    dossiers = pipeline["dossiers"]
    supplier_by_gstin = {s.gstin: s for s in suppliers}

    internal_id_needles = [p.processor_id for p in processors] + [s.supplier_id for s in suppliers]

    def _assert_no_internal_ids(printed, where):
        if not isinstance(printed, str):
            return
        for needle in internal_id_needles:
            assert needle not in printed, (
                f"seed {seed}/{where}: printed field {printed!r} leaks internal id {needle!r}"
            )

    by_supplier_invoices: dict[str, list[tuple[str, str]]] = {}
    ewb_entries: list[tuple[str, str]] = []

    for processor in processors:
        dossier = dossiers[processor.processor_id]
        shipment_by_invoice_doc = {s["invoice_doc_id"]: s for s in dossier.shipments}
        shipment_by_eway_doc = {
            s["eway_doc_id"]: s for s in dossier.shipments if s.get("eway_doc_id")
        }
        docs_by_type: dict[str, list[dict]] = {}
        for doc in dossier.documents:
            docs_by_type.setdefault(doc["doc_type"], []).append(doc)
            for field_name, field in doc["fields"].items():
                _assert_no_internal_ids(field.get("printed"), f"{doc['doc_id']}.{field_name}")

        for doc in docs_by_type.get("cto", []):
            consent_no = doc["fields"]["consent_no"]["printed"]
            assert _CONSENT_NO_RE.match(consent_no), (
                f"seed {seed}/{processor.processor_id}: consent_no {consent_no!r} doesn't match "
                "the issuer-style CTO/<state>/<digits> format"
            )

        for doc in docs_by_type.get("epr_registration", []):
            registration_no = doc["fields"]["registration_no"]["printed"]
            assert _REGISTRATION_NO_RE.match(registration_no), (
                f"seed {seed}/{processor.processor_id}: registration_no {registration_no!r} "
                "doesn't match the issuer-style EPR-REG/<state>/<digits> format"
            )

        # --- weighbridge tickets: per-weighbridge format + chronological ---
        ticket_entries = []
        for doc in docs_by_type.get("weighbridge_slip", []):
            ticket_no = doc["fields"]["ticket_no"]["printed"]
            assert _TICKET_NO_RE.match(ticket_no), (
                f"seed {seed}/{processor.processor_id}: ticket_no {ticket_no!r} doesn't match "
                "the per-weighbridge format"
            )
            assert ticket_no.startswith(processor.weighbridge_code + "-"), (
                f"seed {seed}/{processor.processor_id}: ticket_no {ticket_no!r} doesn't carry "
                "this processor's own weighbridge code"
            )
            ticket_entries.append((doc["fields"]["in_time"]["canonical"], ticket_no))
        ticket_entries.sort(key=lambda t: t[0])
        for idx, (_in_time, ticket_no) in enumerate(ticket_entries, start=1):
            assert ticket_no.endswith(f"-{idx:05d}"), (
                f"seed {seed}/{processor.processor_id}: weighbridge ticket sequence isn't "
                f"chronologically monotonic (expected seq {idx}, got {ticket_no!r})"
            )

        # --- output invoices: per-processor format + chronological ---
        out_entries = []
        for doc in docs_by_type.get("outbound_invoice", []):
            invoice_no = doc["fields"]["invoice_no"]["printed"]
            assert invoice_no.startswith(processor.invoice_prefix + "/25-26/"), (
                f"seed {seed}/{processor.processor_id}: output invoice_no {invoice_no!r} doesn't "
                "carry this processor's own invoice prefix"
            )
            out_entries.append((doc["fields"]["date"]["canonical"], invoice_no))
        out_entries.sort(key=lambda t: t[0])
        for idx, (_date_str, invoice_no) in enumerate(out_entries, start=1):
            assert _invoice_seq(invoice_no) == idx, (
                f"seed {seed}/{processor.processor_id}: output invoice sequence isn't "
                f"chronologically monotonic (expected seq {idx}, got {invoice_no!r})"
            )

        # --- electricity bill consumer_no: one stable all-numeric id per processor ---
        consumer_nos = {
            doc["fields"]["consumer_no"]["printed"]
            for doc in docs_by_type.get("electricity_bill", [])
        }
        assert len(consumer_nos) == 1, (
            f"seed {seed}/{processor.processor_id}: electricity bills don't share one consumer_no"
        )
        (consumer_no,) = consumer_nos
        assert _CONSUMER_NO_RE.match(consumer_no), (
            f"seed {seed}/{processor.processor_id}: consumer_no {consumer_no!r} isn't a "
            "plausible all-numeric DISCOM account number"
        )

        # --- certificates: portal-reference format, anchored on this processor ---
        registration_suffix = processor.registration_no.rsplit("/", 1)[-1]
        for cert in dossier.certificates:
            certificate_id = cert["certificate_id"]
            assert _CERTIFICATE_ID_RE.match(certificate_id), (
                f"seed {seed}/{processor.processor_id}: certificate_id {certificate_id!r} "
                "doesn't match the portal-reference format"
            )
            assert f"/{registration_suffix}/" in certificate_id, (
                f"seed {seed}/{processor.processor_id}: certificate_id {certificate_id!r} "
                "doesn't carry this processor's own registration suffix"
            )

        # --- inbound invoices: per-supplier format, collected for the cross-processor check ---
        for doc in docs_by_type.get("inbound_invoice", []):
            shipment = shipment_by_invoice_doc[doc["doc_id"]]
            if "duplicate_of" in shipment:
                continue
            invoice_no = doc["fields"]["invoice_no"]["printed"]
            supplier = supplier_by_gstin[doc["fields"]["supplier_gstin"]["canonical"]]
            assert invoice_no.startswith(supplier.invoice_prefix + "/25-26/"), (
                f"seed {seed}/{shipment['shipment_id']}: invoice_no {invoice_no!r} doesn't carry "
                "its own supplier's invoice prefix"
            )
            by_supplier_invoices.setdefault(supplier.supplier_id, []).append(
                (doc["fields"]["date"]["canonical"], invoice_no)
            )

        # --- e-way bills: 12-digit format, collected for the cross-processor check ---
        for doc in docs_by_type.get("eway_bill", []):
            shipment = shipment_by_eway_doc.get(doc["doc_id"])
            if shipment is not None and "duplicate_of" in shipment:
                continue
            ewb_no = doc["fields"]["ewb_no"]["printed"]
            assert _EWB_NO_RE.match(ewb_no), (
                f"seed {seed}/{processor.processor_id}: ewb_no {ewb_no!r} isn't a 12-digit "
                "national e-way-bill number"
            )
            ewb_entries.append((doc["fields"]["generated_at"]["canonical"], ewb_no))

    for supplier_id, entries in by_supplier_invoices.items():
        entries.sort(key=lambda t: t[0])
        for idx, (_date_str, invoice_no) in enumerate(entries, start=1):
            assert _invoice_seq(invoice_no) == idx, (
                f"seed {seed}/{supplier_id}: invoice sequence isn't chronologically monotonic "
                f"(expected seq {idx}, got {invoice_no!r})"
            )

    ewb_entries.sort(key=lambda t: t[0])
    ewb_values = [int(ewb_no) for _generated_at, ewb_no in ewb_entries]
    assert ewb_values == sorted(ewb_values), (
        f"seed {seed}: e-way bill numbers aren't strictly increasing with generation time"
    )
    assert len(set(ewb_values)) == len(ewb_values), f"seed {seed}: duplicate e-way bill numbers"
