import pytest

from app.checks import params
from app.checks.mass_balance import check_c2a, check_c2b, verified_inbound_tonnes


def _matched_shipment(**overrides) -> dict:
    base = {
        "shipment_id": "SHP-1",
        "invoice_doc_id": "INV-1",
        "eway_doc_id": "EWAY-1",
        "weighbridge_doc_id": "WB-1",
        "match_status": "matched",
        "distance_km": 110.0,
        "eway_generated_at": "2026-01-14T06:20:00+00:00",
        "eway_valid_until": "2026-01-15T18:29:00+00:00",
        "weighbridge_in_time": "2026-01-14T10:00:00+00:00",  # 30 km/h
        "invoice_qty_t": 100.0,
        "weighbridge_net_t": 99.0,  # within C4 tolerance
    }
    base.update(overrides)
    return base


def test_verified_inbound_tonnes_sums_clean_matched_shipments():
    s1 = _matched_shipment(shipment_id="SHP-1")
    s2 = _matched_shipment(
        shipment_id="SHP-2",
        invoice_doc_id="INV-2",
        eway_doc_id="EWAY-2",
        weighbridge_doc_id="WB-2",
        invoice_qty_t=50.0,
        weighbridge_net_t=49.5,
    )
    total = verified_inbound_tonnes([s1, s2], duplicate_keys={})
    assert total == 99.0 + 49.5


def test_verified_inbound_tonnes_excludes_unmatched():
    s = _matched_shipment(match_status="unmatched", weighbridge_net_t=None)
    assert verified_inbound_tonnes([s], duplicate_keys={}) == 0.0


def test_verified_inbound_tonnes_excludes_c4_failure():
    # Weighbridge net materially below invoice quantity (F3).
    s = _matched_shipment(weighbridge_net_t=75.0)
    assert verified_inbound_tonnes([s], duplicate_keys={}) == 0.0


def test_verified_inbound_tonnes_excludes_c3a_failure():
    # 110 km in 1h = 110 km/h, above the speed ceiling.
    s = _matched_shipment(weighbridge_in_time="2026-01-14T07:20:00+00:00")
    assert verified_inbound_tonnes([s], duplicate_keys={}) == 0.0


def test_verified_inbound_tonnes_excludes_c5_failure():
    s = _matched_shipment()
    duplicate_keys = {"SHP-1": {"keys": ["ewb_no"], "evidence_ids": []}}
    assert verified_inbound_tonnes([s], duplicate_keys) == 0.0


def test_verified_inbound_tonnes_excludes_cited_shipment_id():
    # T10: a confirmed agent finding cites SHP-1 for exclusion even though
    # it passes every deterministic check.
    s = _matched_shipment(shipment_id="SHP-1")
    assert verified_inbound_tonnes([s], duplicate_keys={}) == 99.0
    assert (
        verified_inbound_tonnes([s], duplicate_keys={}, excluded_shipment_ids=frozenset({"SHP-1"}))
        == 0.0
    )


def test_verified_inbound_tonnes_exclusion_only_affects_cited_shipment():
    s1 = _matched_shipment(shipment_id="SHP-1")
    s2 = _matched_shipment(
        shipment_id="SHP-2",
        invoice_doc_id="INV-2",
        eway_doc_id="EWAY-2",
        weighbridge_doc_id="WB-2",
        invoice_qty_t=50.0,
        weighbridge_net_t=49.5,
    )
    total = verified_inbound_tonnes(
        [s1, s2], duplicate_keys={}, excluded_shipment_ids=frozenset({"SHP-1"})
    )
    assert total == 49.5


def test_c2a_passes_when_certified_within_verified_inbound():
    result = check_c2a("PWP-01", certified_t=90.0, verified_inbound_t=100.0)
    assert result.status == "pass"
    assert result.affected_tonnes == 0.0


def test_c2a_fails_when_certified_exceeds_verified_inbound():
    # F1/F2-style shortfall.
    result = check_c2a("PWP-02", certified_t=120.0, verified_inbound_t=80.0)
    assert result.status == "fail"
    assert result.affected_tonnes == 40.0


def test_c2a_passes_at_exactly_the_tolerance_boundary():
    certified_t = 1000.0
    shortfall = certified_t * params.C2A_SHORTFALL_TOL
    result = check_c2a(
        "PWP-08", certified_t=certified_t, verified_inbound_t=certified_t - shortfall
    )
    assert result.status == "pass"
    assert result.affected_tonnes == shortfall
    assert result.measured == certified_t


def test_c2a_fails_just_above_the_tolerance_boundary():
    certified_t = 1000.0
    shortfall = certified_t * params.C2A_SHORTFALL_TOL + 0.01
    result = check_c2a(
        "PWP-08", certified_t=certified_t, verified_inbound_t=certified_t - shortfall
    )
    assert result.status == "fail"


def test_c2a_small_noise_shortfall_passes():
    # PWP-08-style: ~0.53% shortfall from independent per-shipment
    # weighbridge noise, not a seeded issue.
    result = check_c2a("PWP-08", certified_t=3750.0, verified_inbound_t=3729.98)
    assert result.status == "pass"
    assert result.affected_tonnes == pytest.approx(20.02)


def test_c2b_passes_within_yield_ceiling():
    result = check_c2b("PWP-01", output_t=90.0, verified_inbound_t=100.0)
    assert result.status == "pass"
    assert result.severity == "soft"


def test_c2b_warns_above_yield_ceiling():
    limit = 100.0 * params.MAX_YIELD_RECYCLER
    result = check_c2b("PWP-01", output_t=limit + 5.0, verified_inbound_t=100.0)
    assert result.status == "warn"
    assert result.severity == "soft"
    assert result.affected_tonnes == 5.0
