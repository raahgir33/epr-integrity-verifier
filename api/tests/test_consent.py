from app.checks.consent import certificate_passes_c6, check_c6


def _certificate(**overrides) -> dict:
    base = {
        "certificate_id": "CERT-1",
        "category": "I",
        "generation_date": "30/04/2025",
        "quantity_t": 100.0,
    }
    base.update(overrides)
    return base


def test_category_within_permitted_and_within_window_passes():
    cert = _certificate()
    assert certificate_passes_c6(cert, ["I", "III"], "01/04/2022", "31/03/2028") is True
    result = check_c6("PWP-01", [cert], ["I", "III"], "01/04/2022", "31/03/2028")
    assert result.status == "pass"


def test_category_not_permitted_fails():
    # F6: certificate category the CTO does not permit.
    cert = _certificate(category="I")
    assert certificate_passes_c6(cert, ["III"], "01/04/2022", "31/03/2028") is False
    result = check_c6("PWP-09", [cert], ["III"], "01/04/2022", "31/03/2028")
    assert result.status == "fail"
    assert result.affected_tonnes == 100.0
    assert result.evidence_ids == ["CERT-1"]


def test_generation_date_outside_consent_window_fails():
    # Hand-crafted: not exercised by the real dataset (every consent window
    # spans the full FY), but the date-validity sub-rule is real.
    cert = _certificate(generation_date="15/04/2029")
    assert certificate_passes_c6(cert, ["I"], "01/04/2022", "31/03/2028") is False
    result = check_c6("PWP-01", [cert], ["I"], "01/04/2022", "31/03/2028")
    assert result.status == "fail"


def test_no_certificates_is_not_evaluable():
    result = check_c6("PWP-01", [], ["I"], "01/04/2022", "31/03/2028")
    assert result.status == "not_evaluable"
