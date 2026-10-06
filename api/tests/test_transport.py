from app.checks.transport import check_c3a, check_c3b, shipment_passes_c3a, shipment_passes_c3b


def _shipment(**overrides) -> dict:
    base = {
        "shipment_id": "SHP-1",
        "invoice_doc_id": "INV-1",
        "eway_doc_id": "EWAY-1",
        "weighbridge_doc_id": "WB-1",
        "distance_km": 110.0,
        "eway_generated_at": "2026-01-14T06:20:00+00:00",
        "eway_valid_until": "2026-01-15T18:29:00+00:00",
        "weighbridge_in_time": "2026-01-14T10:00:00+00:00",  # 3h40m after generation
        "weighbridge_net_t": 10.0,
    }
    base.update(overrides)
    return base


def test_c3a_passes_within_speed_limit():
    # 110 km in 3h40m = 30 km/h, well under the 55 km/h ceiling.
    s = _shipment()
    assert shipment_passes_c3a(s) is True
    result = check_c3a("PWP-01", [s])
    assert result.status == "pass"
    assert result.affected_tonnes == 0.0


def test_c3a_fails_above_speed_limit():
    # 110 km in 1h = 110 km/h.
    s = _shipment(weighbridge_in_time="2026-01-14T07:20:00+00:00")
    assert shipment_passes_c3a(s) is False
    result = check_c3a("PWP-01", [s])
    assert result.status == "fail"
    assert result.affected_tonnes == 10.0
    assert "WB-1" in result.evidence_ids


def test_c3a_not_evaluable_without_distance():
    s = _shipment(distance_km=None)
    assert shipment_passes_c3a(s) is None
    result = check_c3a("PWP-01", [s])
    assert result.status == "not_evaluable"


def test_c3a_not_evaluable_for_unmatched_shipment():
    s = _shipment(weighbridge_in_time=None)
    assert shipment_passes_c3a(s) is None
    result = check_c3a("PWP-01", [s])
    assert result.status == "not_evaluable"


def test_c3b_passes_within_validity():
    s = _shipment()
    assert shipment_passes_c3b(s) is True
    result = check_c3b("PWP-01", [s])
    assert result.status == "pass"


def test_c3b_fails_after_valid_until():
    s = _shipment(weighbridge_in_time="2026-01-16T00:00:00+00:00")
    assert shipment_passes_c3b(s) is False
    result = check_c3b("PWP-01", [s])
    assert result.status == "fail"
    assert result.affected_tonnes == 10.0


def test_c3b_not_evaluable_without_valid_until():
    s = _shipment(eway_valid_until=None)
    assert shipment_passes_c3b(s) is None
    result = check_c3b("PWP-01", [s])
    assert result.status == "not_evaluable"


def test_mixed_shipments_only_failing_ones_counted():
    good = _shipment(shipment_id="SHP-OK")
    bad = _shipment(
        shipment_id="SHP-BAD",
        invoice_doc_id="INV-2",
        eway_doc_id="EWAY-2",
        weighbridge_doc_id="WB-2",
        weighbridge_in_time="2026-01-14T07:20:00+00:00",
        weighbridge_net_t=5.0,
    )
    result = check_c3a("PWP-01", [good, bad])
    assert result.status == "fail"
    assert result.affected_tonnes == 5.0
    assert result.evidence_ids == ["INV-2", "EWAY-2", "WB-2"]
