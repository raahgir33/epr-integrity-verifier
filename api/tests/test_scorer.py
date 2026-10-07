from app.agents.scorer import (
    apply_soft_signal_bump,
    capacity_limit_t_with_consent,
    generate_narrative,
    risk_band,
    score_processor,
)
from app.models.checks import CheckResult


class _FakeNarrativeClient:
    def __init__(self, summary_text: str):
        self._summary_text = summary_text

    def generate_structured(self, contents, schema, purpose, thinking_level=None):
        return schema(summary=self._summary_text)


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


def _worked_processor_and_certs():
    processor = {
        "processor_id": "PWP-WORKED-FULL",
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
    return processor, certificates


def _two_shipments():
    base = {
        "invoice_doc_id": "INV-1",
        "eway_doc_id": "EWAY-1",
        "weighbridge_doc_id": "WB-1",
        "match_status": "matched",
        "distance_km": 110.0,
        "eway_generated_at": "2026-01-14T06:20:00+00:00",
        "eway_valid_until": "2026-01-15T18:29:00+00:00",
        "weighbridge_in_time": "2026-01-14T10:00:00+00:00",
    }
    s1 = {**base, "shipment_id": "SHP-1", "invoice_qty_t": 500.0, "weighbridge_net_t": 500.0}
    s2 = {**base, "shipment_id": "SHP-2", "invoice_qty_t": 450.0, "weighbridge_net_t": 450.0}
    return [s1, s2]


def test_score_processor_excluded_shipment_ids_reduces_full_stage_figures():
    processor, certificates = _worked_processor_and_certs()
    shipments = _two_shipments()
    check_results = [CheckResult(check_id="C7", status="pass", severity="soft", explanation="x")]

    checks_only = score_processor(processor, certificates, shipments, {}, check_results, "2026-03")
    full = score_processor(
        processor,
        certificates,
        shipments,
        {},
        check_results,
        "2026-03",
        excluded_shipment_ids=frozenset({"SHP-1"}),
    )

    # checks_only: verified_inbound=950, capped by capacity_limit=1200, eligible_certified=900.
    assert checks_only["verified_inbound_t"] == 950.0
    assert checks_only["verifiable_t"] == 900.0
    # full: SHP-1 (500 t) excluded -> verified_inbound=450, now the binding constraint.
    assert full["verified_inbound_t"] == 450.0
    assert full["verifiable_t"] == 450.0
    assert full["unverifiable_t"] == 450.0


def test_score_processor_no_excluded_ids_matches_checks_only_byte_for_byte():
    processor, certificates = _worked_processor_and_certs()
    shipments = _two_shipments()
    check_results = [CheckResult(check_id="C7", status="pass", severity="soft", explanation="x")]

    default_call = score_processor(processor, certificates, shipments, {}, check_results, "2026-03")
    explicit_empty = score_processor(
        processor, certificates, shipments, {}, check_results, "2026-03", frozenset()
    )

    assert default_call == explicit_empty


def test_generate_narrative_passes_through_clean_text():
    score = {
        "processor_id": "PWP-01",
        "certified_t": 900.0,
        "verified_inbound_t": 950.0,
        "capacity_limit_t": 1200.0,
        "verifiable_t": 900.0,
        "unverifiable_t": 0.0,
        "risk_band": "Low",
    }
    client = _FakeNarrativeClient("900.00 t of 900.00 t certified tonnes verified; risk: Low.")

    narrative = generate_narrative(score, client)

    assert narrative == "900.00 t of 900.00 t certified tonnes verified; risk: Low."


def test_generate_narrative_falls_back_to_template_on_invented_number():
    score = {
        "processor_id": "PWP-02",
        "certified_t": 1560.0,
        "verified_inbound_t": 1560.0,
        "capacity_limit_t": 1200.0,
        "verifiable_t": 1200.0,
        "unverifiable_t": 360.0,
        "risk_band": "Medium",
    }
    # 12345.67 never appears anywhere in score — a hallucinated figure.
    client = _FakeNarrativeClient("This processor verified 12345.67 t of certified material.")

    narrative = generate_narrative(score, client)

    assert "12345.67" not in narrative
    assert narrative == (
        "1200.00 t verifiable of 1560.00 t certified (360.00 t unverifiable); risk band: Medium."
    )
