from app.agents.scorer import (
    apply_soft_signal_bump,
    capacity_limit_t_with_consent,
    risk_band,
    score_processor,
)
from app.models.checks import CheckResult


def test_risk_band_boundaries():
    assert risk_band(0.049) == "Low"
    assert risk_band(0.05) == "Medium"
    assert risk_band(0.25) == "Medium"
    assert risk_band(0.2501) == "High"


def test_soft_signal_bump_raises_one_step_only():
    warn = CheckResult(check_id="C7", status="warn", severity="soft", explanation="x")
    assert apply_soft_signal_bump("Low", [warn]) == "Medium"
    assert apply_soft_signal_bump("Medium", [warn]) == "High"
    assert apply_soft_signal_bump("High", [warn]) == "High"


def test_soft_signal_bump_multiple_failures_still_one_step():
    warn_c2b = CheckResult(check_id="C2b", status="warn", severity="soft", explanation="x")
    warn_c7 = CheckResult(check_id="C7", status="warn", severity="soft", explanation="y")
    assert apply_soft_signal_bump("Low", [warn_c2b, warn_c7]) == "Medium"


def test_soft_signal_bump_no_change_when_nothing_failed():
    passed = CheckResult(check_id="C7", status="pass", severity="soft", explanation="x")
    assert apply_soft_signal_bump("Low", [passed]) == "Low"


def test_capacity_limit_zeroed_outside_consent_window():
    # Hand-crafted: consent expires mid-FY, before the as_of_month.
    limit = capacity_limit_t_with_consent(
        capacity_t_per_year=1200.0,
        as_of_month="2026-03",
        consent_valid_from="01/04/2025",
        consent_valid_to="30/09/2025",
    )
    # Only April-September (6 months) of the FY are within consent.
    assert limit == 1200.0 / 12 * 6


def test_score_processor_worked_example_clean():
    processor = {
        "processor_id": "PWP-WORKED",
        "capacity_t_per_year": 1200.0,
        "permitted_categories": ["I"],
        "consent_valid_from": "01/04/2022",
        "consent_valid_to": "31/03/2028",
    }
    certificates = [
        {
            "certificate_id": "CERT-1",
            "category": "I",
            "period_month": "2026-03",
            "quantity_t": 900.0,
        }
    ]
    shipments = [
        {
            "shipment_id": "SHP-1",
            "invoice_doc_id": "INV-1",
            "eway_doc_id": "EWAY-1",
            "weighbridge_doc_id": "WB-1",
            "match_status": "matched",
            "distance_km": 110.0,
            "eway_generated_at": "2026-01-14T06:20:00+00:00",
            "eway_valid_until": "2026-01-15T18:29:00+00:00",
            "weighbridge_in_time": "2026-01-14T10:00:00+00:00",
            "invoice_qty_t": 950.0,
            "weighbridge_net_t": 950.0,
        }
    ]
    check_results = [CheckResult(check_id="C7", status="pass", severity="soft", explanation="x")]

    score = score_processor(processor, certificates, shipments, {}, check_results, "2026-03")

    assert score["certified_t"] == 900.0
    assert score["verified_inbound_t"] == 950.0
    assert score["capacity_limit_t"] == 1200.0
    # min(eligible_certified=900, verified_inbound=950, capacity_limit=1200)
    assert score["verifiable_t"] == 900.0
    assert score["unverifiable_t"] == 0.0
    assert score["risk_band"] == "Low"


def test_score_processor_worked_example_capacity_inflation():
    # F1-style: certified well above verified inbound and capacity.
    processor = {
        "processor_id": "PWP-WORKED-F1",
        "capacity_t_per_year": 1200.0,
        "permitted_categories": ["I"],
        "consent_valid_from": "01/04/2022",
        "consent_valid_to": "31/03/2028",
    }
    certificates = [
        {
            "certificate_id": "CERT-1",
            "category": "I",
            "period_month": "2026-03",
            "quantity_t": 1560.0,
        }
    ]
    shipments = [
        {
            "shipment_id": "SHP-1",
            "invoice_doc_id": "INV-1",
            "eway_doc_id": "EWAY-1",
            "weighbridge_doc_id": "WB-1",
            "match_status": "matched",
            "distance_km": 110.0,
            "eway_generated_at": "2026-01-14T06:20:00+00:00",
            "eway_valid_until": "2026-01-15T18:29:00+00:00",
            "weighbridge_in_time": "2026-01-14T10:00:00+00:00",
            "invoice_qty_t": 1560.0,
            "weighbridge_net_t": 1560.0,
        }
    ]
    check_results = [CheckResult(check_id="C7", status="pass", severity="soft", explanation="x")]

    score = score_processor(processor, certificates, shipments, {}, check_results, "2026-03")

    # min(eligible_certified=1560, verified_inbound=1560, capacity_limit=1200)
    assert score["verifiable_t"] == 1200.0
    assert score["unverifiable_t"] == 360.0
    assert score["risk_band"] == "Medium"  # 360/1560 = 23.1%, within (5%, 25%]
