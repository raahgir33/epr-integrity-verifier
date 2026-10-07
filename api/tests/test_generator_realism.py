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
    net_t can land slightly outside the class's own boundary. 0.15 t
    comfortably covers that noise on either side."""
    tolerance_t = 0.15
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
