from app.checks.consistency import check_c4, shipment_passes_c4


def _shipment(**overrides) -> dict:
    base = {
        "shipment_id": "SHP-1",
        "invoice_doc_id": "INV-1",
        "eway_doc_id": "EWAY-1",
        "weighbridge_doc_id": "WB-1",
        "invoice_qty_t": 100.0,
        "weighbridge_net_t": 99.0,  # 1% below, within 2% tolerance
    }
    base.update(overrides)
    return base


def test_within_tolerance_passes():
    s = _shipment()
    assert shipment_passes_c4(s) is True
    result = check_c4("PWP-04", [s])
    assert result.status == "pass"
    assert result.affected_tonnes == 0.0


def test_materially_below_invoice_fails():
    # F3: weighbridge net 25% below invoice quantity.
    s = _shipment(weighbridge_net_t=75.0)
    assert shipment_passes_c4(s) is False
    result = check_c4("PWP-03", [s])
    assert result.status == "fail"
    assert result.affected_tonnes == 75.0
    assert result.evidence_ids == ["INV-1", "EWAY-1", "WB-1"]


def test_unmatched_shipment_not_evaluable():
    s = _shipment(weighbridge_net_t=None)
    assert shipment_passes_c4(s) is None
    result = check_c4("PWP-01", [s])
    assert result.status == "not_evaluable"


def test_mixed_shipments_only_failing_ones_counted():
    good = _shipment(shipment_id="SHP-OK")
    bad = _shipment(
        shipment_id="SHP-BAD",
        invoice_doc_id="INV-2",
        eway_doc_id="EWAY-2",
        weighbridge_doc_id="WB-2",
        weighbridge_net_t=50.0,
    )
    result = check_c4("PWP-03", [good, bad])
    assert result.status == "fail"
    assert result.affected_tonnes == 50.0
    assert result.evidence_ids == ["INV-2", "EWAY-2", "WB-2"]
