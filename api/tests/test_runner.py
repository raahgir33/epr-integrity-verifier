from app.checks.runner import run_checks_for_processor, run_checks_for_run


def _processor(**overrides) -> dict:
    base = {
        "processor_id": "PWP-01",
        "type": "recycler",
        "capacity_t_per_year": 1200.0,
        "permitted_categories": ["I", "II"],
        "consent_valid_from": "01/04/2022",
        "consent_valid_to": "31/03/2028",
    }
    base.update(overrides)
    return base


def _clean_shipment(**overrides) -> dict:
    base = {
        "shipment_id": "PWP-01-SHP-001",
        "invoice_doc_id": "INV-1",
        "eway_doc_id": "EWAY-1",
        "weighbridge_doc_id": "WB-1",
        "match_status": "matched",
        "distance_km": 110.0,
        "eway_generated_at": "2026-01-14T06:20:00+00:00",
        "eway_valid_until": "2026-01-15T18:29:00+00:00",
        "weighbridge_in_time": "2026-01-14T10:00:00+00:00",
        "invoice_qty_t": 100.0,
        "weighbridge_net_t": 99.0,
        "ewb_no": "EWB-1",
        "invoice_no": "INV-NO-1",
        "supplier_gstin": "GSTIN-1",
        "weighbridge_ticket_no": "TICKET-1",
    }
    base.update(overrides)
    return base


def test_clean_recycler_all_implemented_checks_pass():
    processor = _processor()
    shipments = [_clean_shipment()]
    outputs = [{"doc_id": "OUT-1", "month": "2026-01", "quantity_t": 90.0}]
    energy_monthly = [{"doc_id": "NRG-1", "month": "2026-01", "kwh": 40000.0}]
    certificates = [
        {
            "certificate_id": "CERT-1",
            "category": "I",
            "generation_date": "28/01/2026",
            "period_month": "2026-01",
            "quantity_t": 90.0,
        }
    ]

    results = run_checks_for_processor(
        processor, shipments, outputs, energy_monthly, certificates, {}, "2026-01"
    )
    by_check = {r.check_id: r for r in results}
    assert {r.check_id for r in results} == {
        "C1",
        "C2a",
        "C2b",
        "C3a",
        "C3b",
        "C4",
        "C5",
        "C6",
        "C7",
    }
    for check_id, result in by_check.items():
        assert result.status == "pass", f"{check_id}: expected pass, got {result.status}"


def test_end_of_life_processor_gets_not_evaluable_for_c2b_and_c7():
    processor = _processor(processor_id="PWP-02", type="end_of_life")
    shipments = [_clean_shipment(shipment_id="PWP-02-SHP-001")]
    certificates = [
        {
            "certificate_id": "CERT-2",
            "category": "I",
            "generation_date": "28/01/2026",
            "period_month": "2026-01",
            "quantity_t": 90.0,
        }
    ]

    results = run_checks_for_processor(processor, shipments, [], [], certificates, {}, "2026-01")
    by_check = {r.check_id: r for r in results}
    assert by_check["C2b"].status == "not_evaluable"
    assert by_check["C7"].status == "not_evaluable"
    assert by_check["C1"].status == "pass"


def test_run_checks_for_run_computes_c5_across_processors():
    original = _clean_shipment(
        shipment_id="PWP-01-SHP-001",
        ewb_no="EWB-SHARED",
        invoice_no="INV-SHARED",
        supplier_gstin="GSTIN-SHARED",
    )
    duplicate = _clean_shipment(
        shipment_id="PWP-10-SHP-DUP",
        invoice_doc_id="PWP-10-INV",
        eway_doc_id="PWP-10-EWAY",
        weighbridge_doc_id=None,
        match_status="unmatched",
        ewb_no="EWB-SHARED",
        invoice_no="INV-SHARED",
        supplier_gstin="GSTIN-SHARED",
        weighbridge_ticket_no=None,
        weighbridge_net_t=None,
    )
    processors = [_processor(processor_id="PWP-01"), _processor(processor_id="PWP-10")]
    shipments_by_processor = {"PWP-01": [original], "PWP-10": [duplicate]}

    results_by_processor = run_checks_for_run(
        processors, shipments_by_processor, {}, {}, {}, "2026-01"
    )
    c5_pwp01 = next(r for r in results_by_processor["PWP-01"] if r.check_id == "C5")
    c5_pwp10 = next(r for r in results_by_processor["PWP-10"] if r.check_id == "C5")
    assert c5_pwp01.status == "pass"
    assert c5_pwp10.status == "fail"
